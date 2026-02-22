import logging
import os
import shutil
import tempfile
import yaml
import tarfile
from subprocess import run
from glom import glom
from .toolkit import ExecutionParams, InternalPaths, process_template, assemble_merged_config
from .exceptions import OstrichError

def show_template_help():
    print("""Ostrich Template Generator
Usage: ost template <command> [args]
Commands:
  - list                    : Display available template types
  - describe <type>         : Detailed info for a specific template
  - config <type>           : Print a sample yaml for <type>
  - install <source>        : Add new template from local dir or registry
  - remove <type>           : Uninstall a custom template
  - package <dir>           : Create a distributable archive
  - publish <dir> <dest>    : Bundle and upload to OCI registry
  - search [reg] <query>    : Find templates on remote registries""")

def generate_all_templates(params: ExecutionParams):
    """Main workflow for rendering a template to the scratch directory."""
    kind = params.lookup_config("template.kind")
    biz_name = params.lookup_config("plugin.business_name", "Ostrich Module")
    version = params.lookup_config("plugin.version", "0.0.1")
    
    logging.info("Initiating: %s [%s v%s]", biz_name, kind, version)
    
    source_path = InternalPaths.resolve_template_path(kind)
    
    # helper for saving files
    def persisting_writer(content, target_rel_path, p: ExecutionParams):
        full_dest = os.path.abspath(os.path.join(p.scratch_dir, target_rel_path))
        os.makedirs(os.path.dirname(full_dest), exist_ok=True)
        with open(full_dest, "w") as out:
            out.write(content)

    process_template(source_path, params.raw_manifest_data, params, persisting_writer)

    # Post-processing for directory renaming
    for root, dirs, _ in os.walk(params.scratch_dir):
        if "application-name" in dirs:
            app_id = params.lookup_config("plugin.name", "untitled")
            src = os.path.join(root, "application-name")
            dst = os.path.join(root, app_id)
            shutil.copytree(src, dst, dirs_exist_ok=True)
            shutil.rmtree(src)

def manage_templates(params: ExecutionParams):
    """Router for 'ost template' subcommands."""
    params.parse_cli_flags()
    args = params.extra_args

    if not args or params.show_help:
        show_template_help()
        return

    command = args[0]
    if command in ["list", "ls"]:
        _perform_list()
    elif command == "describe":
        if len(args) < 2: raise OstrichError("Usage: describe <type>")
        _perform_describe(args[1])
    elif command == "install":
        _perform_install(args[1:], params)
    elif command == "remove":
        if len(args) < 2: raise OstrichError("Usage: remove <type>")
        _perform_remove(args[1])
    else:
        # Default behavior: render current directory
        params.initialize_manifest()
        if not params.custom_output:
            params.scratch_dir = params.lookup_config("plugin.name", "out")
        
        _verify_scratch_state(params)
        generate_all_templates(params)

def _verify_scratch_state(p: ExecutionParams):
    if not os.path.exists(p.scratch_dir):
        os.makedirs(p.scratch_dir)
    elif os.listdir(p.scratch_dir):
        if p.recursive_cleanup:
            logging.info("Wiping scratch directory: %s", p.scratch_dir)
            shutil.rmtree(p.scratch_dir)
            os.makedirs(p.scratch_dir)
        elif not p.strictly_initialize:
            raise OstrichError(f"Directory {p.scratch_dir} is occupied. Use --rm or --force.")

def _perform_list():
    logging.info("Registered Local Templates:")
    found = set()
    roots = [InternalPaths.get_builtin_templates(), InternalPaths.get_ext_templates()]
    for r in roots:
        if os.path.exists(r):
            for item in os.listdir(r):
                if item != "global": found.add(item)
    
    for item in sorted(list(found)):
        print(f" * {item}")

def _perform_describe(name):
    print(f"--- Metadata for {name} ---")
    path = InternalPaths.resolve_template_path(name)
    doc = os.path.join(path, "_doc/description.md")
    if os.path.exists(doc):
        with open(doc, 'r') as f:
            print(f.read())
    else:
        print("No offline documentation found.")

def _perform_install(args, params):
    # Logic similar to before but with new path helpers
    pass

def _perform_remove(name):
    target = os.path.join(InternalPaths.get_ext_templates(), name)
    if os.path.lexists(target):
        if os.path.islink(target): os.unlink(target)
        else: shutil.rmtree(target)
        logging.info("Template '%s' purged.", name)
    else:
        logging.warning("Template not found in user extensions.")