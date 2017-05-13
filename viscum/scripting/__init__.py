"""Scripting with python & module manager objects."""

import ast
import symtable
import astor
from viscum.plugin import ModuleCapabilities as ModCap
from viscum.hook import ModuleManagerHookActions
from viscum.scripting.exception import (InvalidModuleError,
                                        DeferScriptLoading,
                                        ScriptSyntaxError,
                                        CancelScriptLoading)


class ModuleManagerScript(object):
    """Script parser and container class."""

    def __init__(self, source_file, module_manager, initialize=False):
        """Initialize.

        Args
        ----
        source_file: str
            File path
        module_manager: ModuleManager
            Reference to module manager
        initialize: bool
            Automatically initialize script
        """
        # module_manager reference
        self._modman = module_manager
        self._sanitizer_logging = None
        # try to open, parse
        with open(source_file, 'r') as f:
            try:
                text = f.read()
                self.sanitized_code =\
                    ModuleManagerScript.sanitize_code(text,
                                                      self._sanitizer_logging)
            except Exception:
                raise

        # create a scope for the script
        self.script_scope = {}

        # flags
        self._executed_once = False
        self._name_set = False

        # misc
        self.name = '?'

        # auto-initialize
        if initialize:
            self.initialize_script()

    @staticmethod
    def sanitize_code(code, logging_function=None):
        """Sanitize an AST by removing statements defined as illegal.

        Scripts should be simple and so are not allowed to import modules,
        for example.
        Args
        ----
        code: TODO what type is this
            Compiled script code
        logging_function: function, NoneType
            Callback for logging
        """
        # sanitize code
        tree = ast.parse(code)
        parsed_code = CodeSanitizer(logging_function).visit(tree)

        # fix code
        ast.fix_missing_locations(parsed_code)

        return parsed_code

    def _parse_more(self, sanitized_code, global_scope):
        """Parse code a bit more, look into symbol table.

        Args
        ----
        sanitized_code: ???
            The compiled and sanitized code
        global_scope: dict
            Scope in which the code is executed
        """
        def parse_symtab(symtab):
            required_modules = set()
            # go through symbols and detect those that have not been assigned
            for symbol in symtab.get_symbols():
                if symbol.is_referenced() and\
                   symbol.is_assigned() is False and\
                   symbol.is_parameter() is False:
                    # tried to reference a symbol but was
                    # never assigned? Investigate
                    name_parts = symbol.get_name().split('__')
                    module_type = name_parts[0]
                    instance_name = ''.join(name_parts[1:])
                    if instance_name != '':
                        symbol_name = '{}-{}'.format(module_type,
                                                     instance_name)
                    else:
                        symbol_name = module_type
                    if symbol_name in self._modman.list_loaded_modules():
                        # this is a module name
                        required_modules.add(symbol_name)
                    elif module_type in self._modman.list_discovered_modules():
                        # this is a module type but it is not loaded
                        # at the moment
                        # if plugin has multi-instance capability, the name
                        # without a suffix accesses the class
                        mod_caps = self._modman.get_module_capabilities(
                            module_type)
                        if ModCap.MultiInstanceAllowed in mod_caps and\
                           instance_name != '':
                            raise DeferScriptLoading({'type': module_type,
                                                      'inst': instance_name})
                        elif ModCap.MultiInstanceAllowed not in mod_caps:
                            raise DeferScriptLoading({'type': module_type,
                                                      'inst': module_type})
                        else:
                            required_modules.add(module_type)
                    elif symbol_name in global_scope:
                        # being provided by the global scope, allowed
                        continue
                    else:
                        # not a module, unknown!
                        raise InvalidModuleError('{} is not a valid module '
                                                 'or variable'
                                                 .format(symbol_name))

            return required_modules

        # de-parse the sanitized AST
        sanitized_text = astor.to_source(sanitized_code)
        symtab = symtable.symtable(sanitized_text, '<string>', 'exec')

        required_modules = set()
        # main code body
        required_modules |= parse_symtab(symtab)

        # go into functions & others
        for tab in symtab.get_children():
            required_modules |= (parse_symtab(tab))

        return required_modules

    def _instrument_code(self, sanitized_code):
        """Insert several custom variables and functions in the code.

        Args
        ----
        sanitized_code: ???
           The sanitized code
        """
        return sanitized_code

    def _script_print_statement(self, *args):
        """Log a print statement executed by script.

        Args
        ----
        args: list
           Argument list
        """
        # try to transform everything in strings
        msg_list = [str(arg) for arg in args]
        message = ''.join(msg_list)

        self._modman.log_message('log_info', 'scripting.{}: {}'
                                 .format(self.name, message))

    def _sanitizer_logging(self, level, message):
        """Log CodeSanitizer object messages.

        Args
        ----
        level: str
           Log level
        message: str
           The message
        """
        self._modman.log_message(level, 'scripting: {}'.format(message))

    def _require_module_instance(self, module_type, instance_name=None):
        """Guard execution by requiring that a specific instance be present.

        If not present, script execution will be deferred until it is
        present.
        Args
        ----
        module_type: str
           Plugin type
        instance_name: str
           Name of the required instance
        """
        # detect if this type of module is available
        if module_type not in self._modman.list_discovered_modules():
            raise InvalidModuleError('module type {} is not available'
                                     .format(module_type))

        # differentiate between multiple instance and single instance
        if ModCap.MultiInstanceAllowed in\
           self._modman.get_module_capabilities(module_type):
            if instance_name is None:
                raise ValueError('must specify an instance name '
                                 'for module of type "{}"'
                                 .format(module_type))

            _inst_name = instance_name
        else:
            _inst_name = module_type

        # check if is loaded, else defer
        if _inst_name not in self._modman.get_loaded_module_list():
            raise DeferScriptLoading({'type': module_type, 'inst': _inst_name})

    def _attach_man_hook(self, hook_name, cb):
        """Attach to manager system hooks.

        Args
        ----
        hook_name: str
            Name of the hook to attach to
        cb: function
            Hook callback
        """
        self._modman.attach_manager_hook(hook_name,
                                         cb,
                                         ModuleManagerHookActions.NO_ACTION,
                                         None)

    def _attach_custom_hook(self, hook_name, cb):
        """Attach to custom hooks.

        Args
        ----
        hook_name: str
            Name of the hook to attach to
        cb: function
            Hook callback
        """
        self._modman.attach_custom_hook(hook_name,
                                        cb,
                                        ModuleManagerHookActions.NO_ACTION,
                                        None)

    def _set_name(self, name):
        """Set a friendly name for logging.

        Args
        ----
        name: str
            A name
        """
        if self._name_set:
            return

        self.name = name
        self._name_set = True

    def _cancel_exec(self, reason=None):
        """Cancel loading for some reason.

        Args
        ----
        reason: str
           A reason for cancelling
        """
        raise CancelScriptLoading(reason)

    def _load_module(self, module_name, **kwargs):
        """Load a plugin.

        Args
        ----
        module_name: str
            Plugin name
        kwargs: list
            Arguments to be passed at loading time
        """
        self._modman.load_module(module_name, **kwargs)

    def initialize_script(self):
        """Initialize the compiled code."""
        if self._executed_once:
            # already initialized (should raise?)
            return

        # TODO: create scope with globals translated from the module manager
        self.script_scope = {'_print_statement': self._script_print_statement,
                             'require_instance': self._require_module_instance,
                             'attach_custom_hook': self._attach_custom_hook,
                             'attach_man_hook': self._attach_man_hook,
                             'set_name': self._set_name,
                             'cancel_exec': self._cancel_exec,
                             'load_module': self._load_module}

        # print self.sanitized_code.body
        # parse code a bit more and detect module usage
        used_modules = self._parse_more(self.sanitized_code, self.script_scope)

        # insert module proxies in the scope
        for mod in used_modules:
            self.script_scope[mod] = ModuleProxy(mod, self._modman)

        # instrument the code with globals & others
        self.instrumented_code = self._instrument_code(self.sanitized_code)

        # execute the body
        self._execute_code(self.instrumented_code)

        # some things should not be allowed after main body execution,
        # remove from scope
        del self.script_scope['set_name']
        del self.script_scope['cancel_exec']

        # flag as initialized
        self._executed_once = True

    def _execute_code(self, instrumented_code):
        """Execute the script body.

        Should only be done once, normally.
        Typically this will attach callbacks and do initialization
        Args
        ----
        instrumented_code: str
           The previously instrumented code
        """
        compiled_script = compile(instrumented_code, '<string>', 'exec')
        exec(compiled_script, self.script_scope)

    def _call_custom_method(self, method_name, *args, **kwargs):
        """Call a method through module manager.

        Args
        ----
        method_name: str
           Name of method
        args: list
           Argument list
        kwargs: dict
           Keyword arguments
        """
        return self._modman.call_module_method(method_name, *args, **kwargs)


class CodeSanitizer(ast.NodeTransformer):
    """Code sanitizer.

    Remove code deemed unsafe or not allowed
    """

    def __init__(self, logging_function=None):
        """Initialize.

        Args
        ----
        logging_function: function
           Callback for logging
        """
        super(CodeSanitizer, self).__init__()
        self._logfn = logging_function

    def log(self, level, message):
        """Log a message if logger function available.

        Args
        ----
        level: str
           Log level
        message: str
           The message
        """
        if self._logfn is not None:
            self._logfn(level, message)

    def visit_Import(self, node):
        """Visit import statements, which will be removed.

        Args
        ----
        node: TODO check type
            A node being visited
        """
        # Import statements not allowed
        raise ScriptSyntaxError('import statements are not allowed')

    def visit_ImportFrom(self, node):
        """Visit ImportFrom statements.

        Args
        ----
        node: TODO check type
            A node being visited
        """
        raise ScriptSyntaxError('import statements are not allowed')

    def visit_Call(self, node):
        """Visit print statements.

        Args
        ----
        node: TODO check type
            A node being visited
        """
        # replace print statement with module manager-based logging
        if node.func.id != 'print':
            return node

        return ast.copy_location(
                ast.Call(
                    func=ast.Name(id='_print_statement',
                                  ctx=ast.Load()),
                    args=node.args,
                    keywords=[]), node)

    def visit_While(self, node):
        """Visit while statements.

        Args
        ----
        node: TODO check type
            A node being visited
        """
        raise ScriptSyntaxError('while statements are not allowed')


class ModuleProxy(object):
    """Module proxy to invoke methods and read properties transparently."""

    def __init__(self, module_name, module_manager, instance_name=None):
        """Initialize.

        Args
        ----
        module_name: str
           Plugin name
        module_manager: ModuleManager
           Reference to the module manager
        instance_name: str
           Name of instance
        """
        self._modman = module_manager
        self._modname = module_name
        self._instname = instance_name

    def get_available_instances(self):
        """Return available instances."""
        module_type, _ = self._get_instance_id()
        return self._modman.get_instance_list_by_type(self._modname)

    def get_instance(self, instance_name):
        """Return a proxy for an instance.

        Args
        ----
        instance_name: str
           Instance name
        """
        module_type, _ = self._get_instance_id()
        mod_cap = self._modman.get_module_capabilities(module_type)

        if mod_cap is not None:
            if ModCap.MultiInstanceAllowed in mod_cap:
                _instance_name = '{}-{}'.format(module_type, instance_name)
            else:
                _instance_name = instance_name
            if _instance_name in self.get_available_instances():
                return ModuleProxy(self._modname, self._modman, instance_name)

        # if we reach here, then the module or instance is not loaded.
        raise DeferScriptLoading({'type': self._modname,
                                  'inst': instance_name})

    def _get_instance_id(self):
        """Retrieve instance name."""
        if self._instname is None:
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

        return (module_type, instance_name)

    def __getattr__(self, name):
        """Search for the requested attribute.

        look into properties and methods
        Args
        ----
        name: str
            Attribute name (property or method)
        """
        # try to get instance name
        module_type, instance_name = self._get_instance_id()
        property_list = self._modman.get_module_property_list(module_type)
        method_list = self._modman.get_module_method_list(module_type)

        if name in property_list:
            # property found, get property value and return
            return self._modman.get_module_property(instance_name, name)
        elif name in method_list:
            # method found
            def method_proxy(*args, **kwargs):
                return self._modman.call_module_method(instance_name,
                                                       name,
                                                       *args,
                                                       **kwargs)

            return method_proxy
        else:
            # not found!
            raise AttributeError
