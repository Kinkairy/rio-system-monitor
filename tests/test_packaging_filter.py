import unittest,importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('packaging_filter',Path(__file__).resolve().parents[1]/'packaging_filter.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class PackagingTests(unittest.TestCase):
 def test_required_modules(self):
  for path in ['PySide6/Qt6Quick.dll','PySide6/Qt6QuickControls2Basic.dll','PySide6/Qt6QuickControls2BasicStyleImpl.dll','PySide6/Qt6QuickControls2Impl.dll','PySide6/Qt6Network.dll','PySide6/Qt6OpenGL.dll','PySide6/Qt6Widgets.dll','PySide6/Qt6Svg.dll','PySide6/qml/QtQml/Models/modelsplugin.dll','PySide6/qml/QtQml/WorkerScript/workerscriptplugin.dll','PySide6/opengl32sw.dll','PySide6/plugins/platforms/qwindows.dll','PySide6/qml/QtQuick/Controls/Basic/Button.qml','PySide6/qml/QtQuick/Controls/impl/qtquickcontrols2implplugin.dll','PySide6/qml/QtQuick/Templates/qtquicktemplates2plugin.dll','PySide6/qml/QtQuick/Layouts/qquicklayoutsplugin.dll','assets/ui/Main.qml']:
   self.assertTrue(m.keep(path),path)
 def test_unused_modules(self):
  for path in ['PySide6/Qt6WebEngineCore.dll','PySide6/Qt6Pdf.dll','PySide6/Qt6ShaderTools.dll','PySide6/plugins/qmltooling/qmldbg_debugger.dll','PySide6/qml/QtQml/StateMachine/qtqmlstatemachineplugin.dll','PySide6/qml/QtQuick/Controls/Basic/plugins.qmltypes','PySide6/Qt6Quick3D.dll','PySide6/Qt6QuickControls2Material.dll','PySide6/qml/QtWebEngine/qmldir','PySide6/qml/QtQuick/VirtualKeyboard/qmldir','PySide6/qml/QtQuick/Controls/Material/Button.qml']:
   self.assertFalse(m.keep(path),path)
