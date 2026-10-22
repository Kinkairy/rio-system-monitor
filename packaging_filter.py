"""Bundle only Qt Quick modules used by Main.qml. Does not alter installed Qt."""
UNUSED_LIBS=('Qt6Web','Qt6Pdf','Qt63D','Qt6Quick3D','Qt6Graphs','Qt6Charts','Qt6DataVisualization','Qt6Multimedia','Qt6SpatialAudio','Qt6Location','Qt6Positioning','Qt6Sensors','Qt6VirtualKeyboard','Qt6QuickDialogs','Qt6RemoteObjects','Qt6TextToSpeech','Qt6Scxml','Qt6Serial')
UNUSED_STYLES=('FluentWinUI3','Fusion','Imagine','Material','Universal','Windows','Native')

def keep(name):
 p=name.replace('\\','/');base=p.rsplit('/',1)[-1]
 if '/qml/' in p:
  module=p.split('/qml/',1)[1]
  if module.startswith('QtQml/') or module.startswith('QtCore/'):return True
  if not module.startswith('QtQuick/'):return False
  rel=module[len('QtQuick/'):]
  if '/' not in rel:return True
  section=rel.split('/',1)[0]
  if section in ('Layouts','Window','Templates'):return True
  if section=='Controls':
   rest=rel[len('Controls/'):]
   return '/' not in rest or rest.startswith(('Basic/','impl/'))
  return False
 if base.startswith(UNUSED_LIBS):return False
 if any(base.startswith('Qt6QuickControls2'+style) for style in UNUSED_STYLES):return False
 if 'qtwebengine' in p.lower() or 'QtWebEngineProcess' in p:return False
 if 'PySide6/translations/' in p:return False # no QTranslator is used; EN/CN strings live in our app
 # JPEG/PNG/Freetype and software-OpenGL fallback deliberately stay.
 return True
