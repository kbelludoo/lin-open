# LIN Core Library - Crystal Implementation
# 
# This module implements the core components of the LIN language:
# - Parser (LIA/LIN syntax)
# - AST (Abstract Syntax Tree)
# - IR (Intermediate Representation)
# - Type Checker
# - Semantic Hash
# - Emitter (code generation for multiple targets)

require "json"

# LIN Header format
LIN_HEADER = "@LIN:L1c:0.2"
LIA_HEADER = "@LIN:L1c:0.2"

# ============================================================================
# AST Definitions
# ============================================================================

struct SchemaFlags
  include JSON::Serializable

  property schema_once : Bool = false
  property lossy : Bool = false
  property ops : String?

  def initialize(@schema_once = false, @lossy = false, @ops = nil)
  end
end

struct SigilTable
  include JSON::Serializable

  property question : String = "if"   # ? = if
  property hash : String = "for"      # # = for
  property caret : String = "ret"     # ^ = ret
  property colon : String = "else"    # : = else

  def initialize(@question = "if", @hash = "for", @caret = "ret", @colon = "else")
  end
end

struct Function
  include JSON::Serializable

  property name : String
  property params : Array(String)
  property body : String

  def initialize(@name, @params, @body)
  end
end

struct Program
  include JSON::Serializable

  property header : String
  property schema_flags : SchemaFlags
  property sigil_table : SigilTable
  property functions : Array(Function)
  property exports : Array(String)

  def initialize(@header, @schema_flags, @sigil_table, @functions, @exports)
  end
end

# ============================================================================
# Parser
# ============================================================================

def parse_lia(source : String) : Program
  lines = source.lines
  raise "Empty source" if lines.empty?

  # Parse header
  header = lines[0].strip
  unless header.starts_with?("@LIN:") || header.starts_with?("@LIA:") || header.starts_with?("@AIL:")
    raise "Invalid header: #{header}"
  end

  # Parse second line with flags and sigils
  raise "Missing schema/sigil line" if lines.size < 2

  schema_line = lines[1].strip
  schema_flags, sigil_table = parse_schema_and_sigils(schema_line)

  # Parse functions and exports
  functions = [] of Function
  exports = [] of String

  lines.skip(2).each do |line|
    line = line.strip
    next if line.empty?

    if line.starts_with?("!")
      # Function definition
      functions << parse_function(line)
    elsif line.starts_with?("=ex{")
      # Export statement
      exports = parse_exports(line)
    end
  end

  Program.new(header, schema_flags, sigil_table, functions, exports)
end

def parse_schema_and_sigils(line : String) : {SchemaFlags, SigilTable}
  schema_once = false
  lossy = false
  ops = nil
  
  # Parse schema flags
  schema_once = true if line.includes?("^schema_once")
  lossy = true if line.includes?("^lossy=true")
  
  # Extract ops value
  if ops_start = line.index("^ops=")
    ops_end = line[ops_start..-1].index(' ') || line.size - ops_start
    ops_value = line[ops_start + 5...ops_start + ops_end]
    ops = ops_value
  end

  # Parse sigil table ~G{?=if #=for ^=ret :else}
  sigil_table = if sigil_start = line.index("~G{")
    if sigil_end = line[sigil_start..-1].index('}')
      sigils = line[sigil_start + 3...sigil_start + sigil_end]
      parse_sigils(sigils)
    else
      raise "Unclosed sigil table"
    end
  else
    # Default sigils
    SigilTable.new
  end

  {SchemaFlags.new(schema_once, lossy, ops), sigil_table}
end

def parse_sigils(sigils : String) : SigilTable
  question = "if"
  hash = "for"
  caret = "ret"
  colon = "else"

  sigils.split.each do |part|
    if part.starts_with?("??")
      question = part[2..-1]
    elsif part.starts_with?("#=")
      hash = part[2..-1]
    elsif part.starts_with?("^=")
      caret = part[2..-1]
    elsif part.starts_with?(":")
      colon = part[1..-1]
    end
  end

  SigilTable.new(question, hash, caret, colon)
end

def parse_function(line : String) : Function
  # Format: !name(params){body}
  raise "Function must start with !" unless line.starts_with?("!")

  rest = line[1..-1]
  paren_start = line.index('(') || raise("Missing ( in function")
  paren_end = line.index(')') || raise("Missing ) in function")
  brace_start = line.index('{') || raise("Missing { in function")
  
  # Find matching closing brace
  depth = 1
  brace_end = nil
  (brace_start + 1...line.size).each do |i|
    c = line[i]
    if c == '{'
      depth += 1
    elsif c == '}'
      depth -= 1
      if depth == 0
        brace_end = i
        break
      end
    end
  end
  raise "Unclosed function body" unless brace_end

  name = rest[...paren_start - 1].strip
  params_str = line[paren_start + 1...paren_end]
  params = params_str.strip.empty? ? [] of String : params_str.split(',').map(&.strip)
  body = line[brace_start + 1...brace_end]

  Function.new(name, params, body)
end

def parse_exports(line : String) : Array(String)
  # Format: =ex{name1,name2,...}
  raise "Invalid export statement" unless line.starts_with?("=ex{")
  
  start = 4 # Skip "=ex{"
  end_idx = line.index('}') || raise("Unclosed export")
  content = line[start...end_idx]
  
  return [] of String if content.strip.empty?
  
  content.split(',').map(&.strip)
end

# ============================================================================
# Type Checker (Basic)
# ============================================================================

def type_check(program : Program) : Nil
  # Basic validation
  program.functions.each do |func|
    raise "Function name cannot be empty" if func.name.empty?
  end
end

# ============================================================================
# Semantic Hash
# ============================================================================

def compute_semantic_hash(program : Program) : String
  # Simple hash implementation using Crystal's built-in hash
  hash_value = program.header.hash ^ program.functions.size.hash
  program.functions.each do |func|
    hash_value ^= func.name.hash ^ func.body.hash
  end
  hash_value.abs.to_s(16)
end

# ============================================================================
# Emitter - Code Generation for Multiple Targets
# ============================================================================

enum Target
  JavaScript
  TypeScript
  Python
  Rust
  Go
  C

  def self.from_str(s : String) : Target
    case s.downcase
    when "js", "javascript" then JavaScript
    when "ts", "typescript" then TypeScript
    when "py", "python" then Python
    when "rs", "rust" then Rust
    when "go" then Go
    when "c" then C
    else raise "Unknown target: #{s}"
    end
  end
end

def emit_code(program : Program, target : Target) : String
  result = case target
  when Target::JavaScript then emit_javascript(program)
  when Target::TypeScript then emit_typescript(program)
  when Target::Python then emit_python(program)
  when Target::Rust then emit_rust_target(program)
  when Target::Go then emit_go(program)
  when Target::C then emit_c(program)
  end
  result || ""
end

def emit_javascript(program : Program) : String
  output = [] of String
  
  # Add LIN header comment
  output << "// Generated by LIN Compiler (Crystal)"
  output << "// Source: #{program.header}"
  output << ""
  
  # Generate functions
  program.functions.each do |func|
    params = func.params.join(", ")
    output << "function #{func.name}(#{params}) {"
    
    # Simple body translation (placeholder - full implementation would parse the body)
    body = translate_body_to_js(func.body, program.sigil_table)
    body.lines.each { |line| output << "  #{line}" }
    
    output << "}"
    output << ""
  end
  
  # Generate exports
  unless program.exports.empty?
    output << "module.exports = {"
    program.exports.each_with_index do |exp, i|
      comma = i < program.exports.size - 1 ? "," : ""
      output << "  #{exp}#{comma}"
    end
    output << "};"
  end
  
  output.join("\n")
end

def emit_typescript(program : Program) : String
  output = [] of String
  
  output << "// Generated by LIN Compiler (Crystal)"
  output << "// Source: #{program.header}"
  output << ""
  
  program.functions.each do |func|
    params = func.params.join(", ")
    output << "export function #{func.name}(#{params}): any {"
    
    body = translate_body_to_js(func.body, program.sigil_table)
    body.lines.each { |line| output << "  #{line}" }
    
    output << "}"
    output << ""
  end
  
  output.join("\n")
end

def emit_python(program : Program) : String
  output = [] of String
  
  output << "# Generated by LIN Compiler (Crystal)"
  output << "# Source: #{program.header}"
  output << ""
  
  program.functions.each do |func|
    params = func.params.join(", ")
    output << "def #{func.name}(#{params}):"
    
    body = translate_body_to_py(func.body, program.sigil_table)
    body.lines.each { |line| output << "    #{line}" }
    output << ""
  end
  
  unless program.exports.empty?
    exports_list = program.exports.map { |s| "\"#{s}\"" }.join(", ")
    output << "__all__ = [#{exports_list}]"
  end
  
  output.join("\n")
end

def emit_rust_target(program : Program) : String
  output = [] of String
  
  output << "// Generated by LIN Compiler (Crystal)"
  output << "// Source: #{program.header}"
  output << ""
  
  program.functions.each do |func|
    params = func.params.map { |p| "#{p}: i64" }.join(", ")
    
    output << "pub fn #{func.name}(#{params}) -> i64 {"
    
    body = translate_body_to_rust(func.body, program.sigil_table)
    body.lines.each { |line| output << "    #{line}" }
    
    output << "}"
    output << ""
  end
  
  output.join("\n")
end

def emit_go(program : Program) : String
  output = [] of String
  
  output << "// Generated by LIN Compiler (Crystal)"
  output << "// Source: #{program.header}"
  output << ""
  output << "package main"
  output << ""
  
  program.functions.each do |func|
    params = func.params.map { |p| "#{p} int64" }.join(", ")
    
    output << "func #{func.name}(#{params}) int64 {"
    
    body = translate_body_to_go(func.body, program.sigil_table)
    body.lines.each { |line| output << "    #{line}" }
    
    output << "}"
    output << ""
  end
  
  output.join("\n")
end

def emit_c(program : Program) : String
  output = [] of String
  
  output << "// Generated by LIN Compiler (Crystal)"
  output << "// Source: #{program.header}"
  output << ""
  
  program.functions.each do |func|
    params = func.params.map { |p| "long #{p}" }.join(", ")
    
    output << "long #{func.name}(#{params}) {"
    
    body = translate_body_to_c(func.body, program.sigil_table)
    body.lines.each { |line| output << "    #{line}" }
    
    output << "}"
    output << ""
  end
  
  output.join("\n")
end

# Simple body translation helpers (placeholder implementations)
def translate_body_to_js(body : String, sigils : SigilTable) : String
  # In a full implementation, this would properly parse and translate
  # For now, do basic sigil replacement
  body.gsub("^return ", "return ")
      .gsub("?(", "if (")
      .gsub("#(", "for (")
      .gsub("){", ") {")
      .gsub(";^", "; return ")
end

def translate_body_to_py(body : String, sigils : SigilTable) : String
  body.gsub("^return ", "return ")
      .gsub("?(", "if ")
      .gsub("#(", "for ")
      .gsub("){", ":")
      .gsub(";^", "; return ")
end

def translate_body_to_rust(body : String, sigils : SigilTable) : String
  body.gsub("^return ", "return ")
      .gsub("?(", "if ")
      .gsub("#(", "for ")
      .gsub("){", ") {")
      .gsub(";^", "; return ")
end

def translate_body_to_go(body : String, sigils : SigilTable) : String
  body.gsub("^return ", "return ")
      .gsub("?(", "if ")
      .gsub("#(", "for ")
      .gsub("){", ") {")
      .gsub(";^", "; return ")
end

def translate_body_to_c(body : String, sigils : SigilTable) : String
  body.gsub("^return ", "return ")
      .gsub("?(", "if ")
      .gsub("#(", "for ")
      .gsub("){", ") {")
      .gsub(";^", "; return ")
end
