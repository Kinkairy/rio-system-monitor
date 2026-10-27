"""Host UI library loader. Modules share the existing engine and component library."""
from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlComponent,QQmlContext

def install_ui(engine, assets):
    engine.addImportPath(str(assets/'ui'))

def create_panel(engine,source,properties,context_properties):
    context=QQmlContext(engine.rootContext(),engine)
    for name,value in context_properties.items():context.setContextProperty(name,value)
    component=QQmlComponent(engine,QUrl.fromLocalFile(str(source)))
    if component.isError():raise RuntimeError('\n'.join(e.toString() for e in component.errors()))
    window=component.createWithInitialProperties(properties,context)
    if window is None:raise RuntimeError('\n'.join(e.toString() for e in component.errors()))
    # Strong references preserve context/JS bindings for the entire panel lifetime.
    return window,(window,context,component)
