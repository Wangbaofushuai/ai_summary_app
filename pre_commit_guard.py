import ast
import sys
import re
from pathlib import Path

class SecurityVisitor(ast.NodeVisitor):
    def __init__(self):
        self.violations = []

    def visit_Call(self, node):
        func_name = ""
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                func_name = f"{node.func.value.id}.{node.func.attr}"
        elif isinstance(node.func, ast.Name):
            func_name = node.func.id

        is_subprocess = func_name.startswith("subprocess.")
        is_os_system = func_name in ("os.system", "os.popen")

        if is_subprocess or is_os_system:
            for arg in node.args:
                self._check_arg(arg, node.lineno)
            for kw in node.keywords:
                self._check_arg(kw.value, node.lineno)
                
        self.generic_visit(node)
        
    def _check_arg(self, arg, line_num):
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            self._check_string(arg.value, line_num)
        elif isinstance(arg, ast.List) or isinstance(arg, ast.Tuple):
            for elt in arg.elts:
                self._check_arg(elt, line_num)
        elif isinstance(arg, ast.JoinedStr):
            for val in arg.values:
                if isinstance(val, ast.Constant) and isinstance(val.value, str):
                    self._check_string(val.value, line_num)
        
    def _check_string(self, s, line_num):
        s_lower = s.lower()
        if re.search(r'\b(pip|npm)\b', s_lower):
            self.violations.append((line_num, f"Prohibited dynamic environment modification containing '{s}'"))

def main():
    project_root = Path(__file__).parent.resolve()
    exclude_dirs = {'.venv', 'node_modules', '__pycache__', '.git', 'tests'}
    
    violations_found = False
    
    # 扫描项目下所有 Python 源码文件
    for py_file in project_root.rglob('*.py'):
        # 忽略虚拟环境、依赖和缓存目录
        if any(part in exclude_dirs for part in py_file.parts):
            continue
            
        # 跳过本脚本自身
        if py_file.name == 'pre_commit_guard.py':
            continue
            
        try:
            with open(py_file, 'r', encoding='utf-8-sig') as f:
                content = f.read()
            
            tree = ast.parse(content, filename=str(py_file))
            lines = content.splitlines()
            
            visitor = SecurityVisitor()
            visitor.visit(tree)
            
            # 使用正则表达式作为 fallback，防止有些动态拼接没被 AST 完全捕捉
            # 同时也检查全局是否违规导入或使用了不被 AST 检查识别的字符串
            for i, line in enumerate(lines, 1):
                if re.search(r'(subprocess\..*?|os\.(system|popen)\(.*?)[\'"]?(pip|npm)\b', line, re.IGNORECASE):
                    # 避免重复报错
                    if not any(v_line == i for v_line, _ in visitor.violations):
                        visitor.violations.append((i, "Suspicious dynamic environment modification (pip/npm) detected by fallback regex"))
            
            if visitor.violations:
                for line_num, msg in visitor.violations:
                    print(f"ERROR: {py_file.relative_to(project_root)}:{line_num}")
                    if line_num <= len(lines):
                        print(f"       {lines[line_num-1].strip()}")
                    print(f"       Rule violation: {msg}")
                    violations_found = True
                    
        except SyntaxError as e:
            print(f"WARNING: Syntax error in {py_file.relative_to(project_root)}: {e}")
        except Exception as e:
            print(f"WARNING: Could not process {py_file.relative_to(project_root)}: {e}")
            
    if violations_found:
        print("\n[FAILED] Pre-commit guard: Code validation FAILED due to violations of AI_DEVELOPMENT_RULES.")
        sys.exit(1)
    else:
        print("\n[PASSED] Pre-commit guard: Code validation PASSED.")
        sys.exit(0)

if __name__ == '__main__':
    main()
