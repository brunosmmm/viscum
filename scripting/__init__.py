"""Scripting with python & module manager objects
"""
import ast
import symtable
import codegen
import time
from periodicpy.plugmgr.plugin import ModuleCapabilities

class InvalidModuleError(Exception):
    pass

class DeferScriptLoading(Exception):
    pass

class ModuleManagerScript(object):
    """Script parser and container class
    """

    def __init__(self, source_file, module_manager, initialize=False):

        #module_manager reference
        self._modman = module_manager

        #try to open, parse
        with open(source_file, 'r') as f:
            try:
                text = f.read()
                self.sanitized_code = ModuleManagerScript.sanitize_code(text,
                                                                        self._sanitizer_logging)
            except Exception:
                raise

        #create a scope for the script
        self.script_scope = {}

        #flags
        self._executed_once = False

        #auto-initialize
        if initialize:
            self.initialize_script()

    @staticmethod
    def sanitize_code(code, logging_function=None):
        """Sanitize an AST by removing statements defined as illegal
           scripts should be simple and so are not allowed to import modules
           for example
        """
        #sanitize code
        parsed_code = CodeSanitizer(logging_function).visit(ast.parse(code))

        #fix code
        ast.fix_missing_locations(parsed_code)

        return parsed_code

    def _parse_more(self, sanitized_code, global_scope):
        """Parse code a bit more, look into symbol table
        """

        def parse_symtab(symtab):
            required_modules = set()
            #go through symbols and detect those that have not been assigned
            for symbol in symtab.get_symbols():
                if symbol.is_referenced() and symbol.is_assigned() == False and symbol.is_parameter() == False:
                    #tried to reference a symbol but was never assigned? Investigate
                    name_parts = symbol.get_name().split('__')
                    module_type = name_parts[0]
                    instance_name = ''.join(name_parts[1:])
                    if instance_name != '':
                        symbol_name = '{}-{}'.format(module_type, instance_name)
                    else:
                        symbol_name = module_type
                    if symbol_name in self._modman.list_loaded_modules():
                        #this is a module name
                        required_modules.add(symbol_name)
                    elif module_type in self._modman.list_discovered_modules():
                        #this is a module type but it is not loaded at the moment
                        #TODO: defer the loading of this script somehow, raise some exception perhaps
                        #if plugin has multi-instance capability, the name without a suffix
                        #accesses the class
                        if ModuleCapabilities.MultiInstanceAllowed in self._modman.get_module_capabilities(module_type) and instance_name != '':
                            raise DeferScriptLoading({'type': module_type, 'inst': instance_name})
                        elif ModuleCapabilities.MultiInstanceAllowed not in self._modman.get_module_capabilities(module_type):
                            raise DeferScriptLoading({'type': module_type, 'inst': module_type})
                        else:
                            required_modules.add(module_type)
                    elif symbol_name in global_scope:
                        #being provided by the global scope, allowed
                        continue
                    else:
                        #not a module, unknown!
                        raise InvalidModuleError('{} is not a valid module or variable'.format(symbol_name))

            return required_modules

        #de-parse the sanitized AST
        sanitized_text = codegen.to_source(sanitized_code)
        symtab = symtable.symtable(sanitized_text, '<string>', 'exec')

        required_modules = set()
        #main code body
        required_modules |= parse_symtab(symtab)

        #go into functions & others
        for tab in symtab.get_children():
            required_modules |= (parse_symtab(tab))

        return required_modules


    def _instrument_code(self, sanitized_code):
        """Insert several custom variables and functions in the code
        """
        return sanitized_code

    def _script_print_statement(self, *args):
        """Logs a print statement executed by script
        """
        #try to transform everything in strings
        msg_list = [str(arg) for arg in args]
        message = ''.join(msg_list)

        self._modman.log_message('log_info', 'scripting: {}'.format(message))

    def _sanitizer_logging(self, level, message):
        """Logging for CodeSanitizer objects
        """
        self._modman.log_message(level, 'scripting: {}'.format(message))

    def initialize_script(self):
        """Initializes the compiled code
        """
        if self._executed_once:
            #already initialized (should raise?)
            return

        #TODO: create scope with globals translated from the module manager
        self.script_scope = {'_print_statement' : self._script_print_statement
        }

        #print self.sanitized_code.body
        #parse code a bit more and detect module usage
        used_modules = self._parse_more(self.sanitized_code, self.script_scope)

        #insert module proxies in the scope
        for mod in used_modules:
            self.script_scope[mod] = ModuleProxy(mod, self._modman)

        #instrument the code with globals & others
        self.instrumented_code = self._instrument_code(self.sanitized_code)

        #execute the body
        self._execute_code(self.instrumented_code)

        #flag as initialized
        self._executed_once = True

    def _execute_code(self, instrumented_code):
        """Executes the script body. Should only be done once, normally
           Typically this will attach callbacks and do initialization
        """
        compiled_script = compile(instrumented_code, '<string>', 'exec')
        exec compiled_script in self.script_scope

    def _call_custom_method(self, method_name, *args, **kwargs):
        """Tries to call method through module manager
        """
        return self._modman.call_module_method(method_name, *args, **kwargs)

class CodeSanitizer(ast.NodeTransformer):
    """Code sanitizer
       Remove code deemed unsafe or not allowed
    """

    def __init__(self, logging_function=None):
        super(CodeSanitizer, self).__init__()
        self._logfn = logging_function

    def log(self, level, message):
        """Log a message if logger function available
        """
        if self._logfn != None:
            self._logfn(level, message)

    def visit_Import(self, node):
        """Visit import statements, which will be removed
        """
        #Import statements not allowed
        self.log('log_warning', 'import statements not allowed')
        return None

    def visit_ImportFrom(self, node):
        self.log('log_warning', 'import statements not allowed')
        return None

    def visit_Print(self, node):
        #replace print statement with module manager-based logging
        return ast.copy_location(ast.Expr(
            value=ast.Call(
                func=ast.Name(id='_print_statement',
                              ctx=ast.Load()),
                args=node.values,
                keywords=[],
                starargs=None,
                kwargs=None)),
            node)


class ModuleProxy(object):
    """Module proxy class to invoke methods and read properties transparently
    """
    def __init__(self, module_name, module_manager, instance_name=None):
        self._modman = module_manager
        self._modname = module_name
        self._instname = instance_name

    def get_available_instances(self):
        return self._modman.get_instance_list_by_type(self._modname)

    def get_instance(self, instance_name):
        _instance_name = '{}-{}'.format(self._modname, instance_name)
        if _instance_name in self.get_available_instances():
            return ModuleProxy(self._modname, self._modman, instance_name)

        raise DeferScriptLoading({'type': self._modname, 'inst': instance_name})

    def __getattr__(self, name):
        #search for the requested attribute, look into properties and methods

        #try to get instance name
        if self._instname == None:
            name_parts = self._modname.split('__')
            module_type = name_parts[0]
            instance_suffix = ''.join(name_parts[1:])
            if instance_suffix != '':
                instance_name = '{}-{}'.format(module_type, instance_suffix)
            else:
                instance_name = module_type
        else:
            module_type = self._modname
            instance_name = self._instname
            instance_name = '{}-{}'.format(module_type, instance_name)

        property_list = self._modman.get_module_property_list(module_type)
        method_list = self._modman.get_module_method_list(module_type)

        if name in property_list:
            #property found, get property value and return
            return self._modman.get_module_property(instance_name, name)
        elif name in method_list:
            #method found
            def method_proxy(*args, **kwargs):
                return self._modman.call_module_method(instance_name, name, *args, **kwargs)

            return method_proxy
        else:
            #not found!
            raise AttributeError
