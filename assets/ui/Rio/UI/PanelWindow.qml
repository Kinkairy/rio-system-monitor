import QtQuick
import QtQuick.Controls

ApplicationWindow {
 id: win
 default property alias panelData: panel.data
 property string language: "zh"
 property bool zh: language === "zh"
 property string heading: ""
 property url brandSource: Qt.resolvedUrl("../../../rio-brand.png")
 property rect brandClipRect: Qt.rect(8,88,240,80)
 readonly property real panelWidth: panel.width
 readonly property real panelHeight: panel.height
 signal languageRequested(string value)
 signal closeRequested()
 function tr(en,cn){return zh?cn:en}
 width:448;height:730;visible:true;color:"transparent"
 flags:Qt.Window|Qt.FramelessWindowHint
 font.family:zh?"Microsoft YaHei UI":"Segoe UI";font.pixelSize:13
 onClosing:function(event){event.accepted=false;closeRequested()}
 // A soft shadow inside the same transparent native window. No system frame or second window.
 Repeater {
  model: 12
  Rectangle { x: 14-index; y: 16-index; width: win.width-28+index*2; height: win.height-30+index*2; radius: 12+index; color: "black"; opacity: (12-index)*0.0024 }
 }
 Rectangle {
  id: panel; x: 14; y: 12; width: win.width-28; height: win.height-28; radius: 12; color: "#111416"
  Item {
   x: 0; y: 0; width: parent.width; height: 66
   DragHandler { target: null; onActiveChanged: if(active) win.startSystemMove() }
   Image { objectName: "rioBrand"; x: 20; y: 22; width: 76; height: 25; source: win.brandSource; fillMode: Image.PreserveAspectFit; sourceSize: win.brandClipRect.x>0 ? Qt.size(256,256) : Qt.size(240,80); sourceClipRect: win.brandClipRect }
   RioText { x: 109; y: 24; text: win.heading; color: "#e9edef"; font.pixelSize: 17 }
   LanguageSelector { language: win.language; onLanguageRequested: function(value){win.languageRequested(value)}; objectName: "languageSelector"; x: panel.width-128; y: 23 }
   CloseButton { zh: win.zh; objectName: "settingsCloseButton"; x: panel.width-43; y: 20; onClicked: { win.closeRequested() } }
  }
  Rectangle { x: 20; y: 65; width: panel.width-40; height: 1; color: "#292f32" }
 }
}
