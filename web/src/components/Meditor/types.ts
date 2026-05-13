import type { JSONSchema7, JSONSchema7Definition, JSONSchema7TypeName } from 'json-schema';

export type DandiModel = Record<string, unknown>
export type DandiModelUnion = DandiModel | DandiModel[];

export type TransformFunction = (model: DandiModel) => unknown;
export type TransformTable = Map<string, TransformFunction>;

export type JSONSchemaUnionType = JSONSchema7Definition | JSONSchema7Definition[];
export type JSONSchemaTypeNameUnion = JSONSchema7TypeName | JSONSchema7TypeName[] | undefined;
export type BasicTypeName = 'number' | 'integer' | 'string' | 'boolean' | 'null';

export interface BasicSchema extends JSONSchema7 {
  type: BasicTypeName;

  // There's likely more fields we can narrow to undefined
  items: undefined;
}

export interface ObjectSchema extends JSONSchema7 {
  type: 'object'
  properties: {
    [key: string]: JSONSchema7Definition;
  };
}

export interface ArraySchema extends JSONSchema7 {
  type: 'array'
  items: JSONSchemaUnionType;
}

export interface ComplexSchema extends JSONSchema7 {
  type: 'object' | 'array'
}

export interface BasicArraySchema extends JSONSchema7 {
  type: 'array';
  items: BasicSchema
}

type SchemaKeyPropertiesIntersection = {
  [key: string]: JSONSchema7Definition;
} & {
  schemaKey: {
    type: 'string';
    const: string;
  };
};

export interface JSONSchema7WithSubSchema extends JSONSchema7 {
  properties: SchemaKeyPropertiesIntersection;
}

export const basicTypes = ['number', 'integer', 'string', 'boolean', 'null'];

// The LinkML JSON Schema generator emits nullable fields as a type union of
// the form [X, "null"] (e.g. ["string", "null"], ["array", "null"]). For the
// purpose of Meditor's basic/complex/array/object classification, treat such
// a union as if the schema's type were just X — nullability is orthogonal to
// which UI to render. Only this exact shape is accepted; genuine multi-type
// unions like ["string", "number"] are still rejected.
const matchesType = (type: JSONSchemaTypeNameUnion, kind: JSONSchema7TypeName): boolean => (
  type === kind
  || (Array.isArray(type)
    && type.includes(kind)
    && type.every((t) => t === kind || t === 'null'))
);

export const isBasicType = (type: JSONSchemaTypeNameUnion): type is BasicTypeName => {
  if (type === undefined) return false;
  if (!Array.isArray(type)) return basicTypes.includes(type);
  // Array form: accept iff it is exactly one basic type, optionally plus "null".
  const nonNull = type.filter((t) => t !== 'null');
  return nonNull.length === 1 && basicTypes.includes(nonNull[0]);
};

export const isJSONSchema = (schema: JSONSchemaUnionType): schema is JSONSchema7 => (
  typeof schema !== 'boolean'
  && !Array.isArray(schema)
);

export const isBasicSchema = (schema: JSONSchemaUnionType): schema is BasicSchema => (
  isJSONSchema(schema)
  && (isBasicType(schema.type))
);

export const isObjectSchema = (schema: JSONSchemaUnionType): schema is ObjectSchema => (
  isJSONSchema(schema) && schema.properties !== undefined && matchesType(schema.type, 'object')
);

export const isArraySchema = (schema: JSONSchemaUnionType): schema is BasicArraySchema => (
  isJSONSchema(schema)
  && schema.items !== undefined
  && matchesType(schema.type, 'array')
);

export const isBasicArraySchema = (schema: JSONSchemaUnionType): schema is BasicArraySchema => (
  isArraySchema(schema) && isBasicSchema(schema.items)
);

export const isEnum = (schema: JSONSchemaUnionType): boolean => (
  isBasicSchema(schema) && schema.enum !== undefined
);

export const isArrayEnum = (schema: JSONSchemaUnionType): boolean => (
  isArraySchema(schema) && schema.items.enum !== undefined
);

export const isRecord = (obj: unknown): obj is Record<string, unknown> => (
  typeof obj === 'object' && obj !== null && !Array.isArray(obj)
);

export const isDandiModel = (given: unknown): given is DandiModel => (
  isRecord(given)
);

export const isDandiModelArray = (given: unknown): given is DandiModel[] => (
  Array.isArray(given) && given.every((entry) => isDandiModel(entry))
);

export const isDandiModelUnion = (given: unknown): given is DandiModelUnion => (
  isDandiModel(given) || isDandiModelArray(given)
);

export const isBasicEditorSchema = (schema: JSONSchemaUnionType): boolean => (
  isBasicSchema(schema) || isBasicArraySchema(schema) || isArrayEnum(schema)
);

export const isComplexEditorSchema = (schema: JSONSchemaUnionType): boolean => (
  !isBasicEditorSchema(schema)
);
