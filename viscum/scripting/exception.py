"""Scripting Exceptions."""


class InvalidModuleError(Exception):
    """Invalid module."""

    pass


class DeferScriptLoading(Exception):
    """Defer script loading."""

    pass


class ScriptSyntaxError(Exception):
    """Script syntax error."""

    pass


class CancelScriptLoading(Exception):
    """Cancel script loading process."""

    pass
