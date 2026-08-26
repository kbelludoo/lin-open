# LIN CLI - Command Line Interface (Crystal)
# 
# Provides CLI commands for:
# - parse: Parse LIA/LIN source to AST
# - check: Type checking and validation
# - hash: Compute semantic hash
# - emit: Compile to target languages (js, ts, py, rs, go, c)

require "./lin_core"
require "json"

def print_usage
  puts "LIN Compiler (Crystal implementation)"
  puts ""
  puts "Usage: lin_cli <command> [options]"
  puts ""
  puts "Commands:"
  puts "  parse <file>                 Parse LIA/LIN file and print AST"
  puts "  check <file>                 Run type checker"
  puts "  hash <file>                  Compute semantic hash"
  puts "  emit <file> --target <lang>  Compile to target language"
  puts "                               Targets: js, ts, py, rs, go, c"
  puts "  help                         Show this help message"
end

def cmd_parse(filepath : String)
  begin
    source = File.read(filepath)
  rescue e : File::NotFoundError
    STDERR.puts "Error reading file #{filepath}: #{e.message}"
    exit 1
  end

  begin
    program = parse_lia(source)
    json_output = JSON.build(String::Builder.new) do |json|
      program.to_json(json)
    end
    puts json_output
  rescue e : Exception
    STDERR.puts "Parse error: #{e.message}"
    exit 1
  end
end

def cmd_check(filepath : String)
  begin
    source = File.read(filepath)
  rescue e : File::NotFoundError
    STDERR.puts "Error reading file #{filepath}: #{e.message}"
    exit 1
  end

  begin
    program = parse_lia(source)
    type_check(program)
    puts "✓ Type check passed"
  rescue e : Exception
    msg = e.message || ""
    error_type = msg.includes?("Type") ? "Type check" : "Parse"
    STDERR.puts "#{error_type} error: #{e.message}"
    exit 1
  end
end

def cmd_hash(filepath : String)
  begin
    source = File.read(filepath)
  rescue e : File::NotFoundError
    STDERR.puts "Error reading file #{filepath}: #{e.message}"
    exit 1
  end

  begin
    program = parse_lia(source)
    puts compute_semantic_hash(program)
  rescue e : Exception
    STDERR.puts "Parse error: #{e.message}"
    exit 1
  end
end

def cmd_emit(filepath : String, target_str : String)
  begin
    source = File.read(filepath)
  rescue e : File::NotFoundError
    STDERR.puts "Error reading file #{filepath}: #{e.message}"
    exit 1
  end

  begin
    target = Target.from_str(target_str)
  rescue e : Exception
    STDERR.puts "Error: #{e.message}"
    STDERR.puts "Available targets: js, ts, py, rs, go, c"
    exit 1
  end

  begin
    program = parse_lia(source)
    code = emit_code(program, target)
    puts code
  rescue e : Exception
    msg = e.message || ""
    error_type = msg.includes?("Parse") ? "Parse" : "Emission"
    STDERR.puts "#{error_type} error: #{e.message}"
    exit 1
  end
end

# Main entry point
if ARGV.empty?
  print_usage
  exit 1
end

command = ARGV[0]

case command
when "parse"
  if ARGV.size < 2
    STDERR.puts "Error: Missing file argument"
    print_usage
    exit 1
  end
  cmd_parse(ARGV[1])
  
when "check"
  if ARGV.size < 2
    STDERR.puts "Error: Missing file argument"
    print_usage
    exit 1
  end
  cmd_check(ARGV[1])
  
when "hash"
  if ARGV.size < 2
    STDERR.puts "Error: Missing file argument"
    print_usage
    exit 1
  end
  cmd_hash(ARGV[1])
  
when "emit"
  if ARGV.size < 4
    STDERR.puts "Error: Missing arguments"
    STDERR.puts "Usage: lin_cli emit <file> --target <lang>"
    print_usage
    exit 1
  end
  file = ARGV[1]
  target_str = ARGV[3] if ARGV[2] == "--target"
  target_str ||= ARGV[2]
  cmd_emit(file, target_str)
  
when "help", "--help", "-h"
  print_usage
  
else
  STDERR.puts "Unknown command: #{command}"
  print_usage
  exit 1
end
