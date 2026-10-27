import QtQuick
import QtQuick.Controls

ApplicationWindow {
 id: win
 default property alias panelData: panel.data
 property string language: "zh"
 property bool zh: language === "zh"
 property string heading: ""
 // Optional header tabs; when given they take the heading's place.
 property var tabs: []
 property int tab: 0
 property url brandSource: Qt.resolvedUrl("../../../rio-brand.png")
 property rect brandClipRect: Qt.rect(8,88,240,80)
 readonly property real panelWidth: panel.width
 readonly property real panelHeight: panel.height
 signal languageRequested(string value)
 signal closeRequested()
 signal tabRequested(int index)
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
   RioText { x: 109; y: 24; visible: win.tabs.length===0; text: win.heading; color: "#e9edef"; font.pixelSize: 17 }
   Row { objectName: "headerTabs"; x: 109; y: 14; height: 46; spacing: 22; visible: win.tabs.length>0
    Repeater { model: win.tabs
     delegate: Item { required property string modelData; required property int index; objectName: "headerTab"+index; width: label.implicitWidth; height: 46
      Accessible.role: Accessible.PageTab; Accessible.name: modelData
      RioText { id: label; y: 10; text: parent.modelData; font.pixelSize: 17; color: parent.index===win.tab ? "#e9edef" : tabHover.hovered ? "#c3ccd0" : "#6f7c83"; Behavior on color { ColorAnimation { duration: 100 } } }
      Rectangle { y: 41; width: parent.width; height: 2; radius: 1; color: "#a7eb52"; visible: parent.index===win.tab }
      HoverHandler { id: tabHover; cursorShape: Qt.PointingHandCursor }
      TapHandler { onTapped: win.tabRequested(parent.index) }
     }
    }
   }
   LanguageSelector { language: win.language; onLanguageRequested: function(value){win.languageRequested(value)}; objectName: "languageSelector"; x: panel.width-128; y: 23 }
   CloseButton { zh: win.zh; objectName: "settingsCloseButton"; x: panel.width-43; y: 20; onClicked: { win.closeRequested() } }
  }
  Rectangle { x: 20; y: 65; width: panel.width-40; height: 1; color: "#292f32" }
 }
}
