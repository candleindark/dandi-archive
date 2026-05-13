import type { JSONSchema } from "@apidevtools/json-schema-ref-parser";
import { cloneDeep } from 'lodash';

const HTML_TAG_LIKE = /<\/?[a-zA-Z][^>\s]*[^>]*>/g;

function escapeHtmlTagLike(s: string): string {
  return s.replace(HTML_TAG_LIKE, t => t.replace(/</g, '\\\\<').replace(/>/g, '\\\\>'));
}

// Convert a Python-flavored regex (as the LinkML JSON Schema generator emits)
// into one JavaScript's RegExp can compile. The differences encountered so
// far are limited to two: `\Z` (end-of-string anchor) becomes `$`, and a
// quantifier with no lower bound `{,N}` becomes `{0,N}`. Other Python-only
// constructs (e.g. inline `(?P<name>...)`) are not in the schema today.
function pythonRegexToJs(p: string): string {
  return p.replace(/\\Z/g, '$').replace(/\{,(\d+)\}/g, '{0,$1}');
}

/**
 * Strip redundant `$ref: "#/$defs/Any"` siblings to `anyOf` from a raw Dandiset
 * JSON Schema in place, before $ref dereferencing.
 *
 * Background: pydantic2linkml encodes Pydantic union ranges per the LinkML
 * "Unions as ranges" guidance, which produces nodes shaped like
 *   { "$ref": "#/$defs/Any", "anyOf": [<branch>, <branch>, ...] }
 * where `Any` is a wildcard def (type: ["null","boolean","object","number",
 * "string"], additionalProperties: true, ...).
 *
 * In JSON Schema 2019-09+, `$ref` siblings are evaluated as a conjunction with
 * the dereferenced target — so the schema's *meaning* is just `anyOf`, since
 * `Any` constrains nothing. But @apidevtools/json-schema-ref-parser preserves
 * those siblings, so after dereferencing we end up with a hybrid schema that
 * carries both the polymorphic primitive `type` array (and additionalProperties
 * true) from `Any` and the `anyOf` branches. json-layout (used by VJSF) cannot
 * compile a fresh form for that hybrid (e.g. when the user clicks ADD ITEM in
 * a complex tab) and throws "reference not found _jl#$defs".
 *
 * Dropping the `$ref` here — before dereference — leaves the equivalent
 * `anyOf`-only shape that json-layout handles natively, while preserving any
 * unrelated sibling keywords such as `description`. The served JSON Schema on
 * disk is unchanged.
 */
export function stripRedundantAnyRefs(schema: unknown): void {
  if (schema === null || typeof schema !== 'object') return;
  const seen = new WeakSet<object>();
  const visit = (node: unknown): void => {
    if (node === null || typeof node !== 'object') return;
    if (seen.has(node as object)) return;
    seen.add(node as object);
    if (Array.isArray(node)) {
      for (const v of node) visit(v);
      return;
    }
    const obj = node as Record<string, unknown>;
    if (obj.$ref === '#/$defs/Any' && Array.isArray(obj.anyOf)) {
      delete obj.$ref;
    }
    for (const v of Object.values(obj)) visit(v);
  };
  visit(schema);
}

function transformInPlace(node: unknown, seen: WeakSet<object>): void {
  if (node === null || typeof node !== 'object') return;
  if (seen.has(node as object)) return;
  seen.add(node as object);
  if (Array.isArray(node)) {
    for (let i = 0; i < node.length; i += 1) {
      const v = node[i];
      if (typeof v === 'string') {
        node[i] = escapeHtmlTagLike(v);
      } else if (v !== null && typeof v === 'object') {
        transformInPlace(v, seen);
      }
    }
  } else {
    const obj = node as Record<string, unknown>;
    for (const k of Object.keys(obj)) {
      const v = obj[k];
      if (typeof v === 'string') {
        obj[k] = k === 'pattern'
          ? pythonRegexToJs(v)
          : escapeHtmlTagLike(v);
      } else if (v !== null && typeof v === 'object') {
        transformInPlace(v, seen);
      }
    }
  }
}

/**
 * Applies various miscellaneous fixes/massages the Dandiset metadata JSON Schema
 * to make it compatible with VJSF.
 *
 * @param schema The Dandiset metadata JSON Schema
 */
export function fixSchema(schema: JSONSchema) {
  // lodash.cloneDeep is used (instead of a JSON round-trip) because the
  // dereferenced schema can contain cycles — e.g. PropertyValue.valueReference
  // is itself a PropertyValue. JSON.stringify cannot handle such cycles.
  const deepCopySchema = cloneDeep(schema) as Record<string, unknown>;

  // Drop the top-level $schema dialect URL. Ajv 2020 (used by Meditor) only
  // ships the 2020-12 meta-schema; an unfamiliar dialect URL (e.g. the
  // draft/2019-09 URL emitted by the LinkML generator) makes Ajv try to load
  // a meta-schema it doesn't have. The basic slice already strips $schema for
  // the same reason — doing it once here covers the complex slice too.
  if (typeof deepCopySchema === 'object' && deepCopySchema !== null) {
    delete deepCopySchema.$schema;
    // Both the basic and complex schema slices retain the top-level $id, so
    // Ajv tries to register the same schema id twice and throws. Drop $id
    // here — it isn't load-bearing for client-side validation.
    delete deepCopySchema.$id;
  }

  // vjsf renders < and > as HTML tags, which breaks rendering of the schema
  // in places like help text. For example, a description like
  //   "This relation should satisfy: dandiset <relation> resource."
  // would get parsed as raw HTML. Escape any substring that looks like an
  // HTML tag inside string values throughout the schema.
  transformInPlace(deepCopySchema, new WeakSet());

  return deepCopySchema;
}
