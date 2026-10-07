// Plain-object equivalents of the Python dataclasses (mdq.py lines 735-817).
// Attribute names are identical to Python; sets are JS Set; None is null.

export class ProfileLoad {
  constructor({ profile = null, source = null, excluded_lines = new Set(), diagnostics = [] } = {}) {
    Object.assign(this, { profile, source, excluded_lines, diagnostics });
  }
}

export class SourceDocument {
  constructor(init) {
    // path, raw (Buffer), text, lines, masked_text, masked_lines, lexical_code_lines (Set),
    // unclosed_fence_line, unclosed_comment_line, unclosed_opaque_blocks, byte_offsets,
    // profile, profile_source, excluded_lines (Set), diagnostics
    Object.assign(this, init);
  }
  get source_hash() {
    return sha256_of(this.raw);
  }
  get profile_hash() {
    return this.profile !== null && this.profile !== undefined ? sha256_of(normalized_json_of(this.profile)) : null;
  }
}

export class Heading { constructor(init) { Object.assign(this, init); } } // start,end,level,text,source
export class Marker { constructor(init) { Object.assign(this, init); } } // line,key
export class TableRow { constructor(init) { Object.assign(this, init); } } // start,end,values,cells
export class MarkdownTable { constructor(init) { Object.assign(this, init); } } // start,end,header_line,headers,rows,under_heading
export class Record {
  constructor(init) {
    // key,start,end,heading,marker,table_row,fields,confidence, diagnostics=[], identity_evidence=[]
    Object.assign(this, { diagnostics: [], identity_evidence: [] }, init);
  }
}

import { sha256, normalized_json } from "./common.mjs";
const sha256_of = sha256;
const normalized_json_of = normalized_json;
