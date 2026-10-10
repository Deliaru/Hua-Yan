# 复用自 JUE 赛前代码 src/jue/discovery/expr.py（只允许 attrs.x；evaluate(source, attrs: dict, boolean=False)）
"""Small, validated expression language for template preconditions and rule scores."""
import ast
import operator
from functools import lru_cache

_BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
_COMPARE = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
            ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge}


@lru_cache(maxsize=256)
def compile_expr(source):
    tree = ast.parse(source, mode='eval')
    def validate(node):
        if isinstance(node, ast.Expression):
            validate(node.body)
        elif isinstance(node, ast.Constant) and isinstance(node.value, (int, float, str, bool, type(None))):
            pass
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == 'attrs' and not node.attr.startswith('_'):
            pass
        elif isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
            validate(node.left); validate(node.right)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.Not, ast.USub, ast.UAdd)):
            validate(node.operand)
        elif isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
            for value in node.values: validate(value)
        elif isinstance(node, ast.Compare) and all(type(op) in _COMPARE for op in node.ops):
            for value in [node.left, *node.comparators]: validate(value)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ('min', 'max') and node.args and not node.keywords:
            for value in node.args: validate(value)
        else:
            raise ValueError(f'Unsupported expression syntax: {source}')
    validate(tree)
    return tree.body


def evaluate(source, attrs, boolean=False):
    if source is None:
        return True if boolean else None
    def visit(node):
        if isinstance(node, ast.Constant): return node.value
        if isinstance(node, ast.Attribute): return attrs[node.attr]
        if isinstance(node, ast.BinOp): return _BINARY[type(node.op)](visit(node.left), visit(node.right))
        if isinstance(node, ast.UnaryOp):
            value = visit(node.operand)
            return not value if isinstance(node.op, ast.Not) else -value if isinstance(node.op, ast.USub) else +value
        if isinstance(node, ast.BoolOp):
            return all(visit(value) for value in node.values) if isinstance(node.op, ast.And) else any(visit(value) for value in node.values)
        if isinstance(node, ast.Compare):
            left = visit(node.left)
            for op, right in zip(node.ops, node.comparators):
                right = visit(right)
                if not _COMPARE[type(op)](left, right): return False
                left = right
            return True
        values = [visit(arg) for arg in node.args]
        return min(values) if node.func.id == 'min' else max(values)
    try:
        result = visit(compile_expr(source))
    except (KeyError, ZeroDivisionError):
        return False if boolean else None
    return bool(result) if boolean else result
