from __future__ import annotations

import datetime
import logging
import os

from django.conf import settings
from django.contrib.postgres.indexes import HashIndex
from django.core.validators import RegexValidator
from django.db import models
from django_extensions.db.models import TimeStampedModel

from dandiapi.api.models.metadata import PublishableMetadataMixin

from .dandiset import Dandiset

logger = logging.getLogger(__name__)

if settings.DANDI_ALLOW_LOCALHOST_URLS:
    # If this environment variable is set, the pydantic model will allow URLs with localhost
    # in them. This is important for development and testing environments, where URLs will
    # frequently point to localhost.
    os.environ['DANDI_ALLOW_LOCALHOST_URLS'] = 'True'

from dandischema.metadata import aggregate_assets_summary


class VersionMetadata(PublishableMetadataMixin, TimeStampedModel):
    metadata = models.JSONField(default=dict)
    name = models.CharField(max_length=300)

    class Meta:
        indexes = [
            HashIndex(fields=['metadata']),
            HashIndex(fields=['name']),
        ]

    @property
    def references(self) -> int:
        return self.versions.count()

    def __str__(self) -> str:
        return self.name


def _get_default_version() -> str:
    # This cannot be a lambda, as migrations cannot serialize those
    return Version.make_version()


class Version(TimeStampedModel):
    VERSION_REGEX = r'(0\.\d{6}\.\d{4})|draft'

    class Status(models.TextChoices):
        PENDING = 'Pending'
        VALIDATING = 'Validating'
        VALID = 'Valid'
        INVALID = 'Invalid'
        PUBLISHED = 'Published'

    dandiset = models.ForeignKey(Dandiset, related_name='versions', on_delete=models.CASCADE)
    metadata = models.ForeignKey(VersionMetadata, related_name='versions', on_delete=models.CASCADE)
    version = models.CharField(
        max_length=13,
        validators=[RegexValidator(f'^{VERSION_REGEX}$')],
        default=_get_default_version,
    )  # TODO: rename this?
    doi = models.CharField(max_length=64, null=True, blank=True)
    """Track the validation status of this version, without considering assets"""
    status = models.CharField(
        max_length=10,
        default=Status.PENDING,
        choices=Status.choices,
    )
    validation_error = models.TextField(default='', blank=True)

    class Meta:
        unique_together = ['dandiset', 'version']

    @property
    def asset_count(self):
        return self.assets.count()

    @property
    def name(self):
        return self.metadata.name

    @property
    def size(self):
        return self.assets.aggregate(size=models.Sum('blob__size'))['size'] or 0

    @property
    def valid(self) -> bool:
        if self.status != Version.Status.VALID:
            return False

        # Import here to avoid dependency cycle
        from .asset import Asset

        # Return False if any asset is not VALID
        return not self.assets.filter(~models.Q(status=Asset.Status.VALID)).exists()

    @property
    def publish_status(self) -> Version.Status:
        if self.status != Version.Status.VALID:
            return self.status

        # Import here to avoid dependency cycle
        from .asset import Asset

        invalid_asset = self.assets.filter(~models.Q(status=Asset.Status.VALID)).first()
        if invalid_asset:
            return Version.Status.INVALID

        return Version.Status.VALID

    @property
    def publish_validation_error(self) -> str:
        if self.validation_error:
            return self.validation_error

        # Import here to avoid dependency cycle
        from .asset import Asset

        # Assets that are not VALID (could be pending, validating, or invalid)
        invalid_assets = self.assets.filter(status=Asset.Status.INVALID).count()
        if invalid_assets > 0:
            return f'{invalid_assets} invalid asset metadatas'

        # Assets that have not yet been validated (could be pending or validating)
        unvalidated_assets = self.assets.filter(
            ~(models.Q(status=Asset.Status.VALID) | models.Q(status=Asset.Status.INVALID))
        ).count()
        if unvalidated_assets > 0:
            return f'{unvalidated_assets} assets have not been validated yet'

        # No error == ''
        return ''

    @staticmethod
    def datetime_to_version(time: datetime.datetime) -> str:
        return time.strftime('0.%y%m%d.%H%M')

    @classmethod
    def make_version(cls, dandiset: Dandiset = None) -> str:
        versions: models.Manager = dandiset.versions if dandiset else cls.objects

        time = datetime.datetime.utcnow()
        # increment time until there are no collisions
        while True:
            version = cls.datetime_to_version(time)
            collision = versions.filter(version=version).exists()
            if not collision:
                break
            time += datetime.timedelta(minutes=1)

        return version

    @property
    def publish_version(self):
        """
        Generate a published version + metadata without saving it.

        This is useful to validate version metadata without saving it.
        """
        # Create the published model
        published_version = Version(
            dandiset=self.dandiset,
            metadata=self.metadata,
            status=Version.Status.VALID,
        )

        now = datetime.datetime.utcnow()
        # Recompute the metadata and inject the publishedBy and datePublished fields
        published_metadata, _ = VersionMetadata.objects.get_or_create(
            name=self.metadata.name,
            metadata={
                **published_version._populate_metadata(version_with_assets=self),
                'publishedBy': self.metadata.published_by(now),
                'datePublished': now.isoformat(),
            },
        )
        published_version.metadata = published_metadata

        return published_version

    @classmethod
    def citation(cls, metadata):
        year = datetime.datetime.now().year
        name = metadata['name'].rstrip('.')
        url = metadata['url']
        version = metadata['version']
        # If we can't find any contributors, use this citation format
        citation = f'{name} ({year}). (Version {version}) [Data set]. DANDI archive. {url}'
        if 'contributor' in metadata and metadata['contributor']:
            cl = '; '.join(
                [
                    val['name']
                    for val in metadata['contributor']
                    if 'includeInCitation' in val and val['includeInCitation']
                ]
            )
            if cl:
                citation = (
                    f'{cl} ({year}) {name} (Version {version}) [Data set]. DANDI archive. {url}'
                )
        return citation

    @classmethod
    def strip_metadata(cls, metadata):
        """Strip away computed fields from a metadata dict."""
        computed_fields = [
            'name',
            'identifier',
            'version',
            'id',
            'url',
            'assetsSummary',
            'citation',
            'doi',
            'datePublished',
            'publishedBy',
            'manifestLocation',
        ]
        return {key: metadata[key] for key in metadata if key not in computed_fields}

    def _populate_metadata(self, version_with_assets: Version = None):

        # When validating a draft version, we create a published version without saving it,
        # calculate it's metadata, and validate that metadata. However, assetsSummary is computed
        # based on the assets that belong to the dummy published version, which has not had assets
        # copied to it yet. To get around this, version_with_assets is the draft version that
        # should be used to look up the assets for the assetsSummary.
        if version_with_assets is None:
            version_with_assets = self

        # When running _populate_metadata on an unsaved Version, self.assets is not available.
        # Only compute the asset-based properties if this Version has an id, which means it's saved.
        summary = {
            'numberOfBytes': 0,
            'numberOfFiles': 0,
        }
        if version_with_assets.id:
            try:
                summary = aggregate_assets_summary(
                    [asset.metadata.metadata for asset in version_with_assets.assets.all()]
                )
            except Exception:
                # The assets summary aggregation may fail if any asset metadata is invalid.
                # If so, just use the placeholder summary.
                logger.error('Error calculating assetsSummary', exc_info=1)

        # Import here to avoid dependency cycle
        from dandiapi.api.manifests import manifest_location

        metadata = {
            **self.metadata.metadata,
            'manifestLocation': manifest_location(self),
            'name': self.metadata.name,
            'identifier': f'DANDI:{self.dandiset.identifier}',
            'version': self.version,
            'id': f'DANDI:{self.dandiset.identifier}/{self.version}',
            'url': f'https://dandiarchive.org/dandiset/{self.dandiset.identifier}/{self.version}',
            'assetsSummary': summary,
        }
        metadata['citation'] = self.citation(metadata)
        if self.doi:
            metadata['doi'] = self.doi
        if 'schemaVersion' in metadata:
            schema_version = metadata['schemaVersion']
            metadata['@context'] = (
                'https://raw.githubusercontent.com/dandi/schema/master/releases/'
                f'{schema_version}/context.json'
            )
        return metadata

    def save(self, *args, **kwargs):
        metadata = self._populate_metadata()
        new, created = VersionMetadata.objects.get_or_create(
            name=self.metadata.name,
            metadata=metadata,
        )

        if created:
            new.save()

        self.metadata = new
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f'{self.dandiset.identifier}/{self.version}'
