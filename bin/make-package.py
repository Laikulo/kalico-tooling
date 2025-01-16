#!/usr/bin/python3

import ast
from pprint import pprint as pp

import pathlib
import difflib
import shutil
import logging

from glob import glob

from typing import List, Optional

import sys

logging.basicConfig(level=logging.INFO)

top_level_py = [ pathlib.Path(f).stem for f in glob('klippy/*.py') ]
top_level_modules = top_level_py + [ pathlib.Path(f).parent.stem for f in glob('klippy/*/__init__.py') ]

logging.debug(f"Top level: {top_level_modules}")

class ImportRewriter(ast.NodeTransformer):

    def __init__(self, modlist, tln, depth):
        super(ast.NodeTransformer, self)
        self.modifiedImports = set()
        self.__mod_change_list = modlist 
        self.__top_level_names = tln
        self.__depth = depth

    def visit_Import(self, node):
        return self._process_import(node)
    def visit_ImportFrom(self, node):
        return self._process_import(node)

    def _process_import(self, node):
        if not self.contains_klippy(node, self.__depth):
            return node
        module : Optional[str]
        klippy_names : List[ast.alias] = []
        python_names : List[ast.alias] = []
        if type(node) == ast.ImportFrom:
            module = node.module
        else:
            module = None
        for imported_name in node.names:
            if self.name_is_klippy(imported_name, self.__depth):
                klippy_names.append(imported_name)
            else:
                python_names.append(imported_name)

        # Now that we have the names, we need to group up the klippy ones, as each module gets its own import
        klippy_imports = {}

        for klippy_name in klippy_names:
            name_segments = klippy_name.name.split(".")
            if len(name_segments) == 1:
                # Only a single segment, Don't need to split because of the name
                name_pkg = module or ''
                name_mod = name_segments[0]
            else:
                name_pkg = ".".join(name_segments[:-1])
                name_mod = name_segments[-1]
                # Track this modification, we'll have to adjust things because of it
                self.modifiedImports.add((klippy_name.name, name_mod))

            if name_pkg not in klippy_imports:
                klippy_imports[name_pkg] = []

            klippy_imports[name_pkg].append(name_mod)
        new_nodes = []
        if module:
            if python_names:
                new_nodes.append(ast.ImportFrom(module, python_names, self.__depth))
        else:
            if python_names:
                new_nodes.append(ast.Import(python_names))

        for im_pkg, im_names in klippy_imports.items():
            new_nodes.append(ast.ImportFrom(
                im_pkg,
                [ ast.alias(n) for n in im_names ],
                self.__depth
            ))

        self.__mod_change_list.add((node, tuple(new_nodes)))
        logging.info(f"Rewrote an import at {node.lineno}: {ast.unparse(node)} -> {ast.unparse(new_nodes)}")

    def contains_klippy(self, node, depth) -> bool:
        """
        Returns true if any imported names are from klippy
        """
        if type(node) == ast.ImportFrom:
            if node.level == 0 and node.module is not None and node.module.split(".")[0] in self.__top_level_names:
                return True
        for name in node.names:
            if self.name_is_klippy(name, depth):
                return True
        return False

    def name_is_klippy(self, name, depth):
        return name.name.split('.')[0] in self.__top_level_names

    def is_klippy(self, node, depth):
        klippy: Optional[bool] = None
        # For ImportFrom's, we also have to check if the "module" is one of ours
        if type(node) == ast.ImportFrom:
            if node.level == 0 and node.module is not None and node.module.split(".")[0] in self.__top_level_names:
                return True
        for name in node.names:
            name_is_klippy = name.name.split('.')[0] in self.__top_level_names
            if klippy is not None:
                if name_is_klippy != klippy:
                    print(ast.unparse(node))
                    raise ValueError(f"Mixed import! {name.name}")
            else:
                klippy = name_is_klippy
        return klippy

class ImportedThingFixer(ast.NodeTransformer):
    def __init__(self, replacement_list, to_map):
        super(ast.NodeTransformer, self)
        self.__replacements = replacement_list
        self.__to_map = to_map

    def visit_Attribute(self, node):
        elements = self.walk_attribute_chain(node)
        if elements in self.__to_map:
            new_node = ast.Name(id=self.__to_map[elements])
            self.__replacements.add((node,(new_node,)))
            logging.info(f"Rewrote name {ast.unparse(node)} -> {ast.unparse(new_node)}")
            return new_node
        # Non matching node. Dive down in case something deeper matches
        if type(node.value) == ast.Attribute:
            node.value = self.visit_Attribute(node.value)
        elif type(node.value) == ast.Name:
            pass
        return node

    def walk_attribute_chain(self, node, chain: List[str] = None):
        # Walk down an attribute chain until we find a Name.
        # This is probably not efficient, but some other look-ahead will be needed
        if chain is None:
            chain = []
        chain.append(node.attr)
        if type(node.value) == ast.Attribute:
            return self.walk_attribute_chain(node.value, chain)
        elif type(node.value) == ast.Name:
            chain.append(node.value.id)
            return tuple(chain)
        else:
            return ()
        
def walk_py_dir(dirname, namepath=None, top_level_names=None):
    logging.debug(f"Walking {dirname}")
    if namepath is not None:
        depth = len(namepath)
    else:
        depth = 0
        namepath = []

    if top_level_names is None:
        top_level_names = []

    py_here = [ pathlib.Path(f).stem for f in glob(f'{dirname}/*.py') ]
    packages_here = [ pathlib.Path(f).parent.stem for f in glob(f'{dirname}/*/__init__.py')]

    if depth == 0:
        top_level_names = py_here + packages_here
    
    for f in py_here:
        logging.debug(f"Processing: {dirname}/{f}.py")
        do_py(f'{dirname}/{f}.py', namepath + [f], top_level_names)
    for p in packages_here:
        walk_py_dir(f'{dirname}/{p}', namepath + [p], top_level_names)


def do_py(path, namepath, tln):
    node_replacements = set()
    depth = len(namepath)
    with open(path, "r") as insrc:
        intxt = insrc.read()
    kast = ast.parse(intxt)
    imprw = ImportRewriter(node_replacements, top_level_modules, depth)
    imprw.visit(kast)
    import_map={ tuple(reversed(mi[0].split('.'))):mi[1] for mi in imprw.modifiedImports }
    if imprw.modifiedImports:
        fixer = ImportedThingFixer(node_replacements, import_map)
        fixer.visit(kast)
        ast.fix_missing_locations(kast)
    if node_replacements:
        outtxt = apply_node_changes(intxt, node_replacements)
        with open(path, "w") as outfile:
            outfile.write(outtxt)
            outfile.truncate()

def apply_node_changes(input_text, nodes_to_change):
    # Sort nodes based on the line number of the node to replace
    sorted_nodes = list(nodes_to_change)
    sorted_nodes.sort(key=lambda nr: nr[0].lineno)
    
    current_src_lineno=1
    input_lines=input_text.split("\n")
    output_lines=[]
    
    for node_change in sorted_nodes:
        old_node = node_change[0]
        new_nodes = node_change[1]
        if current_src_lineno > old_node.lineno:
            raise RuntimeError("Nodes out of order")
        pre_block = input_lines[current_src_lineno-1:old_node.lineno-1]
        current_src_lineno=old_node.lineno
        output_lines += pre_block
        # At this point, all lines before the block to replace have been passed.
        # Now we want to identify the number of characters to transfer
        # Nodes can potentially be less than a line, or more than one line.
        if old_node.lineno != old_node.end_lineno:
            raise RuntimeError("Asked to replace a multiline node")
        # The code below only covers the single line case
        node_prefix=input_lines[current_src_lineno-1][:old_node.col_offset]
        if old_node.end_col_offset is None:
            node_suffix=''
        else:
            node_suffix=input_lines[current_src_lineno-1][old_node.end_col_offset:]

        if node_suffix or node_prefix:
            if len(new_nodes) == 1:
                output_lines.append(f'{node_prefix}{ast.unparse(new_nodes[0])}{node_suffix}')

            else:
                raise RuntimeError("Prefix/suffix on multi insert not supported")
        else:
            for nn in new_nodes:
                output_lines.append(ast.unparse(nn))
        current_src_lineno+=1
    output_lines += input_lines[current_src_lineno-1:]
    return "\n".join(output_lines)
        
target_klippy=sys.argv[1] if len(sys.argv) > 0 else "klippy"
walk_py_dir(sys.argv[1])

