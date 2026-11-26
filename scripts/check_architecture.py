"""Static production dependency contract. Does not import or execute product code."""

import ast
from collections import namedtuple
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POLICY = Path('scripts/architecture_policy.json')
MODULES = {'runtime', 'audiences', 'campaigns', 'creative', 'learning', 'reasoning',
           'reviews', 'conversations', 'engagements', 'youtube'}
DEPENDENCIES = {
    'campaigns': {'audiences', 'creative'}, 'creative': {'reasoning', 'audiences'},
    'reviews': {'audiences', 'campaigns', 'creative', 'runtime'},
    'conversations': {'reasoning', 'runtime', 'audiences', 'campaigns'},
    'engagements': {'campaigns'},
}
ROLES = {'domain', 'ports', 'application', 'public_api', 'workflow', 'adapter',
         'composition', 'entrypoint', 'transport', 'infrastructure', 'contracts', 'wrapper'}
ALLOWED = {
    'domain': {'domain', 'contracts'},
    'ports': {'domain', 'ports', 'contracts'},
    'application': {'domain', 'ports', 'application', 'public_api', 'workflow', 'contracts'},
    'public_api': {'domain', 'ports', 'application', 'public_api', 'workflow', 'contracts'},
    'workflow': {'public_api', 'workflow', 'contracts'},
    'adapter': {'public_api', 'adapter', 'infrastructure', 'contracts'},
    'infrastructure': {'infrastructure', 'contracts'},
    'contracts': {'contracts'},
    'composition': ROLES - {'entrypoint', 'wrapper'},
    'wrapper': {'entrypoint', 'public_api'},
    'entrypoint': {'composition', 'entrypoint', 'application', 'public_api',
                   'transport', 'infrastructure', 'contracts'},
    'transport': {'application', 'public_api', 'infrastructure', 'contracts'},
}
# Exact module names, not every module that happens to ship with Python.
# Mixed I/O modules require named value imports so their effectful namespace
# cannot be smuggled into a core layer through an alternate stdlib spelling.
VALUE_IMPORTS = {
    'collections': {'Counter'}, 'collections.abc': {'Callable'},
    'csv': {'DictReader', 'DictWriter', 'reader', 'writer'},
    'dataclasses': {'asdict', 'dataclass', 'replace'},
    'decimal': {'Decimal', 'InvalidOperation'},
    'datetime': {'date', 'datetime', 'timedelta', 'timezone'},
    'difflib': {'get_close_matches'},
    'hashlib': {'sha256'}, 'html': {'escape'},
    'json': {'loads', 'dumps', 'load', 'dump', 'JSONDecodeError'},
    'math': {'isfinite', 'isclose', 'ceil', 'floor'}, 'random': {'Random'},
    're': {'compile', 'match', 'search', 'fullmatch', 'sub'},
    'typing': {'Any', 'ContextManager', 'Protocol'}, 'unicodedata': {'normalize'},
    'urllib.parse': {'urlparse', 'urlsplit', 'parse_qs'},
}
COORDINATION_IMPORTS = {
    'contextlib': {'contextmanager'}, 'contextvars': {'ContextVar'},
    'copy': {'deepcopy'}, 'secrets': {'token_urlsafe'},
    'threading': {'Lock', 'RLock'}, 'time': {'time', 'monotonic'},
}
VALUE_SYMBOLS = {'io': {'StringIO', 'BytesIO'}, 'uuid': {'UUID'}}


def standard_import_allowed(role, module, symbol):
    if symbol and symbol.startswith('_'):
        return False
    modules = dict(VALUE_IMPORTS)
    symbols = dict(VALUE_SYMBOLS)
    if role not in {'domain', 'contracts'}:
        modules.update(COORDINATION_IMPORTS)
    if role in {'ports', 'entrypoint'}:
        symbols['pathlib'] = {'Path'}
    if role in {'entrypoint', 'transport'}:
        modules['argparse'] = {'ArgumentParser'}
    if role == 'entrypoint':
        modules['contextlib'] = modules['contextlib'] | {'ExitStack'}
        modules['threading'] = modules['threading'] | {'Thread', 'Event'}
    if role == 'transport':
        # Only the installed server protocol and static-asset dependencies.
        # This does not admit client networking, provider SDKs or persistence.
        symbols['pathlib'] = {'Path'}
        symbols['http.server'] = {'BaseHTTPRequestHandler', 'ThreadingHTTPServer'}
        modules['mimetypes'] = {'guess_type'}
        modules['contextlib'] = modules['contextlib'] | {'ExitStack'}
        modules['threading'] = modules['threading'] | {'Thread', 'Event'}
    if module in symbols:
        return symbol in symbols[module]
    if module in modules and (symbol is None or symbol in modules[module]):
        return True
    # Python's from-package import can load a submodule. Do not let an allowed
    # parent package admit arbitrary children (for example from json import tool).
    return symbol is not None and module + '.' + symbol in modules


Ref = namedtuple('Ref', 'module symbol line')
Problem = namedtuple('Problem', 'module rule target line message')


def module_name(path):
    parts = list(path.with_suffix('').parts)
    if parts[-1] == '__init__':
        parts.pop()
    return '.'.join(parts)


def owner(module):
    parts = module.split('.')
    return parts[1] if len(parts) > 1 else '(root)'


def references(tree, module, package=False):
    """Normalize relative/absolute imports, retaining the imported symbol."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(Ref(item.name, None, node.lineno) for item in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = module.split('.') if package else module.split('.')[:-1]
                base = '.'.join(parts[:len(parts) - node.level + 1])
                if node.module:
                    base += '.' + node.module
            else:
                base = node.module or ''
            found.extend(Ref(base, item.name, node.lineno) for item in node.names)
    return found


class Inventory:
    def __init__(self, sources, roles):
        self.sources, self.roles = sources, roles
        self.trees = {name: ast.parse(source, filename=name) for name, (source, _) in sources.items()}
        self.bindings = {}
        for name, tree in self.trees.items():
            bindings = {}
            # Only top-level bindings can implement a public export. Conditional or
            # computed exports are deliberately unresolved, rather than certified.
            for node in tree.body:
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    refs = references(ast.Module(body=[node], type_ignores=[]), name, sources[name][1])
                    for item, ref in zip(node.names, refs):
                        local = item.asname or item.name.split('.')[0]
                        bindings[local] = (ref.module, ref.symbol)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    bindings[node.name] = ('@local', name)
                elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    for target in targets:
                        if isinstance(target, ast.Name):
                            if isinstance(node.value, ast.Name):
                                bindings[target.id] = bindings.get(node.value.id)
                            else:
                                bindings[target.id] = ('@local', name)
                        else:
                            # Unpacking can overwrite an earlier imported value.
                            # No tuple/list/starred origin inference is attempted.
                            for child in ast.walk(target):
                                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                                    bindings[child.id] = None
                else:
                    # A conditional module-level write can replace an earlier
                    # pure export at runtime. Invalidate it rather than keeping
                    # the earlier convenient origin. Do not enter nested scopes.
                    def invalidate(child):
                        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                            bindings[child.name] = None
                            return
                        if isinstance(child, (ast.Import, ast.ImportFrom)):
                            for item in child.names:
                                bindings[item.asname or item.name.split('.')[0]] = None
                        if isinstance(child, ast.Name) and isinstance(child.ctx, (ast.Store, ast.Del)):
                            bindings[child.id] = None
                        for descendant in ast.iter_child_nodes(child):
                            invalidate(descendant)
                    invalidate(node)
            self.bindings[name] = bindings

    def target(self, ref):
        candidate = ref.module + '.' + ref.symbol if ref.symbol else ref.module
        if candidate in self.sources:
            return candidate, None
        return ref.module, ref.symbol

    def initialization_targets(self, importer, target):
        """Include newly entered package initializers, not active own ancestors.

        Importing a.b.child also initializes a and a.b. An importing module
        already inside a.b necessarily entered those ancestors first; adding
        reverse edges to them would invent a cycle for ordinary sibling imports.
        """
        targets = {target} if target in self.sources else set()
        parts = target.split('.')
        for length in range(1, len(parts)):
            parent = '.'.join(parts[:length])
            if parent in self.sources and self.sources[parent][1]:
                if importer != parent and not importer.startswith(parent + '.'):
                    targets.add(parent)
        return targets

    def origin(self, module, symbol, trail=()):
        key = (module, symbol)
        if key in trail or symbol is None or symbol == '*':
            return None
        binding = self.bindings.get(module, {}).get(symbol)
        if binding is None:
            return None
        target, name = binding
        if target == '@local':
            return name
        return self.origin(target, name, trail + (key,))

    def problems(self, source, module, package=False):
        role = self.roles.get(module)
        if role not in ROLES:
            return [Problem(module, 'classification', module, 1, 'Unclassified production module')]
        tree = ast.parse(source, filename=module)
        found = []

        def reject(rule, target, line, message):
            found.append(Problem(module, rule, target, line, message))

        if role == 'wrapper':
            for node in tree.body:
                forwarding = isinstance(node, ast.ImportFrom) and node.level == 0 and (node.module or '').startswith('acquisition.')
                docstring = isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
                launch = (isinstance(node, ast.If) and ast.dump(node, include_attributes=False) == ast.dump(
                    ast.parse('if __name__ == "__main__":\n    main()').body[0], include_attributes=False))
                if not (forwarding or docstring or launch):
                    reject('wrapper', module, node.lineno, 'Compatibility wrappers may only forward named exports and launch main')

        for ref in references(tree, module, package):
            target, symbol = self.target(ref)
            label = target + ('.' + symbol if symbol else '')
            if symbol == '*':
                reject('wildcard', label, ref.line, 'Wildcard imports hide dependency origins')
                continue
            if not target.startswith('acquisition'):
                root = target.split('.')[0]
                if root == 'importlib' or label in {'builtins.__import__', 'builtins.exec', 'builtins.eval'}:
                    reject('dynamic-import', label, ref.line, 'Dynamic imports/code hide production dependencies')
                    continue
                if root in {'tests', 'scripts', 'test'} or root.startswith('test_'):
                    reject('nonproduction', label, ref.line, 'Production may not import tests or scripts')
                elif role in {'domain', 'contracts', 'ports', 'application', 'workflow', 'public_api', 'entrypoint', 'transport'}:
                    if not standard_import_allowed(role, target, symbol):
                        rule = 'pure-import' if role in {'domain', 'contracts'} else 'infrastructure'
                        reject(rule, label, ref.line, 'Import is outside the declared value/coordination contracts')
                continue
            if target not in self.roles:
                reject('unknown-target', label, ref.line, 'Unknown production dependency')
                continue
            target_role = self.roles[target]
            source_owner, target_owner = owner(module), owner(target)
            if source_owner in MODULES:
                if target_owner not in {source_owner, 'contracts'} | DEPENDENCIES.get(source_owner, set()):
                    reject('module-dependency', label, ref.line, 'Business module dependency is not declared')
                    continue
            # Business module consumers always use named public exports. This
            # also rejects namespace imports, whose later attribute use is opaque.
            if target_owner in MODULES and source_owner != target_owner:
                if target != 'acquisition.' + target_owner or symbol is None or symbol.startswith('_'):
                    reject('private-api', label, ref.line, 'Cross-module import must use a named public API export')
                    continue
                if self.origin(target, symbol) is None:
                    reject('unresolved-export', label, ref.line, 'Public export has no statically resolvable origin')
                    continue
            effective_role = target_role
            if role in {'domain', 'ports', 'contracts'} and target_role == 'public_api':
                origin = self.origin(target, symbol)
                effective_role = self.roles.get(origin)
            if effective_role not in ALLOWED[role]:
                reject('layer', label, ref.line,
                       f'{role} may not depend on {effective_role or "unresolved export"}')
        # Explicit dynamic import mechanisms cannot evade the import graph.
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else None
                if name in {'__import__', 'exec', 'eval', 'import_module'}:
                    reject('dynamic-import', name, node.lineno, 'Dynamic code/imports are outside the static contract')
        return found


def eager_tree(tree):
    """Import initialization edges, excluding explicitly deferred function bodies."""
    nodes = []

    def walk(node):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            return
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            nodes.append(node)
        for child in ast.iter_child_nodes(node):
            walk(child)

    walk(tree)
    return ast.Module(body=nodes, type_ignores=[])


def inventory(root, roles):
    sources = {}
    paths = {}
    for path in sorted((root / 'src/acquisition').rglob('*.py')):
        name = module_name(path.relative_to(root / 'src'))
        if name in sources:
            raise ValueError(f'Ambiguous production module {name}: both a file and package exist')
        sources[name] = (path.read_text(), path.name == '__init__.py')
        paths[name] = path.relative_to(root).as_posix()
    if not sources:
        raise ValueError('No production modules found under src/acquisition')
    return Inventory(sources, roles), paths


def cycles(graph):
    """One deterministic witness per strongly connected component."""
    index, stack, active, indices, low, result = 0, [], set(), {}, {}, []

    def visit(node):
        nonlocal index
        indices[node] = low[node] = index
        index += 1
        stack.append(node)
        active.add(node)
        for child in sorted(graph.get(node, ())):
            if child not in indices:
                visit(child)
                low[node] = min(low[node], low[child])
            elif child in active:
                low[node] = min(low[node], indices[child])
        if low[node] == indices[node]:
            component = []
            while True:
                child = stack.pop()
                active.remove(child)
                component.append(child)
                if child == node:
                    break
            if len(component) > 1 or node in graph.get(node, ()):
                result.append(sorted(component))

    for node in sorted(graph):
        if node not in indices:
            visit(node)
    return result


def analyze(root, policy):
    roles = policy['modules']
    inv, paths = inventory(root, roles)
    problems = []
    for module, (source, package) in inv.sources.items():
        problems.extend(inv.problems(source, module, package))
    for module in sorted(set(roles) - set(inv.sources)):
        problems.append(Problem(module, 'stale-classification', module, 1, 'Classification has no production file'))
    graph, packages = {}, {}
    for module, tree in inv.trees.items():
        graph.setdefault(module, set())
        packages.setdefault(owner(module), set())
        for ref in references(tree, module, inv.sources[module][1]):
            target, _ = inv.target(ref)
            if target in inv.sources and owner(target) != owner(module):
                packages[owner(module)].add(owner(target))
        for ref in references(eager_tree(tree), module, inv.sources[module][1]):
            target, _ = inv.target(ref)
            graph[module].update(inv.initialization_targets(module, target))
    for graph_name, edges in [('module-cycle', graph), ('package-cycle', packages)]:
        for component in cycles(edges):
            # A package importing itself is natural; a Python module doing so is not.
            target = ', '.join(str(item) for item in component)
            problems.append(Problem(component[0] if graph_name == 'module-cycle' else 'acquisition.' + str(component[0]),
                                    graph_name, target, 1, 'Dependency cycle component: ' + target))
    return problems, paths


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate policy key: {key}')
        result[key] = value
    return result


def check(root):
    try:
        policy = json.loads((root / POLICY).read_text(), object_pairs_hook=unique_object)
        if not isinstance(policy, dict) or set(policy) != {'version', 'modules', 'exceptions'}:
            raise ValueError('Expected version, modules and exceptions policy fields')
        if type(policy.get('version')) is not int or policy['version'] != 1 or not isinstance(policy.get('modules'), dict):
            raise ValueError('Expected architecture policy version 1 with an exact module inventory')
        if set(policy['modules'].values()) - ROLES:
            raise ValueError('Unknown architecture role')
        problems, paths = analyze(root, policy)
        if type(policy['exceptions']) is not list or policy['exceptions']:
            raise ValueError('Architecture migration is closed; exceptions must be an empty list')
        errors = []
        for problem in problems:
            path = paths.get(problem.module, problem.module)
            errors.append(f'{path}:{problem.line}: [{problem.rule}] {problem.message}: {problem.target}')
        return sorted(set(errors))
    except (OSError, ValueError, KeyError, TypeError, SyntaxError) as error:
        return [f'Invalid architecture policy or source: {error}']


def violations(source, module):
    """Raw diagnostics for mutation tests. Never applies migration exceptions."""
    policy = json.loads((ROOT / POLICY).read_text())
    inv, _ = inventory(ROOT, policy['modules'])
    return [f'{p.line}: [{p.rule}] {p.message}: {p.target}' for p in inv.problems(source, module)]


if __name__ == '__main__':
    errors = check(ROOT)
    if errors:
        print('\n'.join(errors))
    else:
        policy = json.loads((ROOT / POLICY).read_text())
        print(f'Architecture: passed; {len(policy["modules"])} classified modules, '
              f'{len(policy["exceptions"])} explicit temporary dependency exceptions')
    raise SystemExit(bool(errors))
