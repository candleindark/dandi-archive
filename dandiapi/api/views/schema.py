from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from dandischema.models import Asset, Dandiset, PublishedAsset, PublishedDandiset
from dandischema.utils import TransitionalGenerateJsonSchema
from drf_yasg.utils import swagger_auto_schema
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response

if TYPE_CHECKING:
    from rest_framework.request import Request


# Experimentally serve the LinkML-derived Dandiset JSON Schema instead of the
# one generated from the Pydantic Dandiset model. The file lives in the
# linkml-auto-converted branch of the local dandi-schema checkout.
_LINKML_DANDISET_SCHEMA_PATH = Path(
    '/Users/isaac/Developer/Dartmouth/dandi-schema/dandischema/models_linkml/dandiset.json'
)


_model_name_mapping = {
    m.__name__: m
    for m in [
        Dandiset,
        Asset,
        PublishedDandiset,
        PublishedAsset,
    ]
}


class SchemaQuerySerializer(serializers.Serializer):
    model = serializers.ChoiceField(choices=list(_model_name_mapping))


@swagger_auto_schema(method='GET', operation_summary='List schema models')
@api_view(['GET'])
def schema_list_view(request: Request) -> Response:
    """Return the list of models which can be requested via the schema endpoint."""
    return Response(_model_name_mapping.keys())


@swagger_auto_schema(
    method='GET',
    operation_summary='Get model schema',
    operation_description='Returns the JSON Schema of the requested metadata model',
    query_serializer=SchemaQuerySerializer,
)
@api_view(['GET'])
def schema_view(request: Request) -> Response:
    """
    Return the JSON Schema of the requested metadata model.

    This endpoint returns the JSON Schema of the requested metadata model
    as it is defined in this DANDI archive instance, with instance specific
    parameters such as instance name and DOI prefix.
    """
    serializer = SchemaQuerySerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)

    model_name = serializer.validated_data['model']
    if model_name == 'Dandiset':
        with _LINKML_DANDISET_SCHEMA_PATH.open() as f:
            schema = json.load(f)
        return Response(schema)

    # Generate the JSON schema using the same approach as dandischema
    model_class = _model_name_mapping[model_name]
    schema = model_class.model_json_schema(schema_generator=TransitionalGenerateJsonSchema)

    return Response(schema)
