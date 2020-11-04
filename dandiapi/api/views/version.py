from guardian.utils import get_40x_or_None
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework_extensions.mixins import DetailSerializerMixin, NestedViewSetMixin

from dandiapi.api.models import Asset, Version
from dandiapi.api.views.common import DandiPagination
from dandiapi.api.views.serializers import VersionDetailSerializer, VersionSerializer


class VersionViewSet(NestedViewSetMixin, DetailSerializerMixin, ReadOnlyModelViewSet):
    queryset = Version.objects.all().select_related('dandiset')
    queryset_detail = queryset

    permission_classes = [IsAuthenticatedOrReadOnly]
    serializer_class = VersionSerializer
    serializer_detail_class = VersionDetailSerializer
    pagination_class = DandiPagination

    lookup_field = 'version'
    lookup_value_regex = Version.VERSION_REGEX

    @action(detail=True, methods=['POST'], serializer_class=None)
    # @permission_required_or_403('owner', (Dandiset, 'pk', 'dandiset__pk'))
    def publish(self, request, **kwargs):
        old_version = self.get_object()

        # TODO @permission_required doesn't work on methods
        # https://github.com/django-guardian/django-guardian/issues/723
        response = get_40x_or_None(request, ['owner'], old_version.dandiset, return_403=True)
        if response:
            return response

        new_version = Version.copy(old_version)
        new_version.save()
        for old_asset in old_version.assets.all():
            new_asset = Asset.copy(old_asset, new_version)
            new_asset.save()
        serializer = VersionSerializer(new_version)
        return Response(serializer.data, status=status.HTTP_200_OK)