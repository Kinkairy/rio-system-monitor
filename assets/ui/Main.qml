import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
 id: win
 width: 448; height: 558; visible: true; color: "transparent"
 flags: Qt.Window | Qt.FramelessWindowHint
 title: "RIO System Monitor"
 property bool zh: bridge.language === "zh"
 function tr(en, cn) { return zh ? cn : en }
 onClosing: function(close) { close.accepted = false; bridge.hideWindow() }
 onVisibleChanged: bridge.setPreviewVisible(visible)
 font.family: "Segoe UI"
 font.pixelSize: 13
 component RioText: Text { font.family: "Segoe UI" }
 component ActionButton: Button {
  id: b
  property color fill: "#24282b"
  property color ink: "#e5e8e9"
  implicitHeight: 38
  background: Rectangle { radius: 8; color: b.down ? Qt.darker(b.fill,1.18) : b.hovered ? Qt.lighter(b.fill,1.12) : b.fill; border.width: b.activeFocus ? 1 : 0; border.color: "#a7eb52" }
  contentItem: RioText { text: b.text; color: b.ink; font: b.font; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
 }
 component RioSwitch: Switch {
  id: sw
  implicitWidth: 42; implicitHeight: 24
  indicator: Rectangle {
   width: 42; height: 24; radius: 12; color: sw.checked ? "#a7eb52" : "#343a3e"
   Behavior on color { ColorAnimation { duration: 130 } }
   Rectangle { width: 18; height: 18; y: 3; x: sw.checked ? 21 : 3; radius: 9; color: sw.checked ? "#18200e" : "#a4acb0"; Behavior on x { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } } }
  }
 }
 // A soft shadow inside the same transparent native window. No system frame or second window.
 Repeater {
  model: 12
  Rectangle { x: 14-index; y: 16-index; width: 420+index*2; height: 528+index*2; radius: 12+index; color: "black"; opacity: (12-index)*0.0024 }
 }
 Rectangle {
  id: panel; x: 14; y: 12; width: 420; height: 530; radius: 12; color: "#111416"
  Item {
   x: 0; y: 0; width: parent.width; height: 66
   DragHandler { target: null; onActiveChanged: if(active) win.startSystemMove() }
   Image { x: 20; y: 22; width: 76; height: 25; source: "../rio-brand.png"; fillMode: Image.PreserveAspectFit; sourceClipRect: Qt.rect(8,88,240,80) }
   RioText { x: 109; y: 24; text: win.tr("Settings","设置"); color: "#e9edef"; font.pixelSize: 17 }
   Rectangle {
    x: 292; y: 23; width: 76; height: 26; radius: 6; color: "#272d30"
    Rectangle { x: win.zh ? 39 : 2; y: 2; width: 35; height: 22; radius: 4; color: "#ffdf32"; Behavior on x { NumberAnimation { duration: 140 } } }
    Row { anchors.fill: parent; Repeater { model: ["EN","CN"]; delegate: RioText { required property string modelData; required property int index; width: 38; height: 26; text: modelData; color: (win.zh === (index===1)) ? "#161a10" : "#a6adb1"; font.pixelSize: 10; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; MouseArea { anchors.fill: parent; onClicked: bridge.setLanguage(index===1 ? "zh":"en") } } } }
   }
   ActionButton { x: 377; y: 20; width: 26; height: 30; fill: "transparent"; text: "×"; font.pixelSize: 22; onClicked: bridge.hideWindow() }
  }
  Rectangle { x: 20; y: 65; width: 380; height: 1; color: "#292f32" }
  Image { id: screen; x: 20; y: 88; width: 170; height: 170; source: "image://monitor/frame?"+bridge.frameId; cache: false; smooth: true; rotation: rotationSlider.value; fillMode: Image.PreserveAspectFit }
  RioText { x: 212; y: 119; text: win.tr("Screen rotation","屏幕方向"); color: "#dce3e6"; font.pixelSize: 13 }
  RioText { x: 212; y: 147; text: Math.round(rotationSlider.value)+"°"; color: "#a7eb52"; font.pixelSize: 24; font.weight: Font.DemiBold }
  Slider {
   id: rotationSlider; objectName: "rotationSlider"; x: 204; y: 188; width: 194; height: 32; from: 0; to: 359; stepSize: 1; value: bridge.rotation
   background: Rectangle { x: rotationSlider.leftPadding; y: rotationSlider.topPadding+rotationSlider.availableHeight/2-height/2; width: rotationSlider.availableWidth; height: 4; radius: 2; color: "#343d40" }
   handle: Rectangle { x: rotationSlider.leftPadding+rotationSlider.visualPosition*(rotationSlider.availableWidth-width); y: rotationSlider.topPadding+rotationSlider.availableHeight/2-height/2; width: 18; height: 18; radius: 9; color: rotationSlider.pressed ? "#c6ff7e" : "#a7eb52" }
  }
  RioText { x: 24; y: 280; text: win.tr("Weather","天气"); color: "#dce3e6" }
  ActionButton { x: 20; y: 306; width: 332; text: bridge.cityLabel || win.tr("Select city","选择城市"); onClicked: { cityPopup.open(); searchField.forceActiveFocus() } }
  ActionButton { x: 362; y: 306; width: 38; text: "↻"; ink: "#a7eb52"; font.pixelSize: 22; onClicked: consentPopup.open() }
  RioText { x: 24; y: 373; text: win.tr("Start at login","登录后自动启动"); color: "#dce3e6" }
  RioSwitch { id: autoSwitch; objectName: "autoSwitch"; x: 358; y: 367; checked: bridge.autostart }
  RioText { x: 24; y: 418; text: win.tr("Start minimized","启动后最小化"); color: "#dce3e6" }
  RioSwitch { id: hiddenSwitch; x: 358; y: 412; checked: bridge.startHidden }
  Rectangle { x: 20; y: 458; width: 380; height: 1; color: "#292f32" }
  RioText { x: 24; y: 489; text: "Your system. At a glance."; color: "#899398"; font.pixelSize: 10 }
  ActionButton { x: 310; y: 477; width: 90; height: 34; text: bridge.saved ? win.tr("Saved","已保存") : win.tr("Save","保存"); fill: "#a7eb52"; ink: "#17210f"; onClicked: bridge.saveSettings(Math.round(rotationSlider.value),autoSwitch.checked,hiddenSwitch.checked) }
 }
 Popup {
  id: cityPopup; popupType: Popup.Item; objectName: "cityPopup"; parent: Overlay.overlay; x: (win.width-width)/2; y: (win.height-height)/2; width: 376; height: 356; modal: true; focus: true; padding: 20
  background: Rectangle { color: "#1a2024"; radius: 12; border.color: "#354047" }
  Overlay.modal: Rectangle { color: "#99080a0c" }
  ColumnLayout {
   anchors.fill: parent; spacing: 14
   RowLayout { Layout.fillWidth: true; RioText { text: win.tr("Choose your city","选择城市"); color: "#edf0f2"; font.pixelSize: 17; Layout.fillWidth: true } ActionButton { text: "×"; fill: "transparent"; Layout.preferredWidth: 26; implicitHeight: 26; onClicked: cityPopup.close() } }
   TextField {
    id: searchField; objectName: "searchField"; Layout.fillWidth: true; implicitHeight: 40; placeholderText: win.tr("Search city or region","搜索城市或地区"); color: "#edf0f2"; placeholderTextColor: "#7f8d95"; selectByMouse: true; leftPadding: 12; font.pixelSize: 13
    background: Rectangle { color: "#11171b"; radius: 7; border.color: searchField.activeFocus ? "#a7eb52" : "#354047"; border.width: 1 }
    onAccepted: bridge.searchCities(text)
   }
   ListView {
    Layout.fillWidth: true; Layout.fillHeight: true; clip: true; spacing: 5; model: bridge.cityResults
    delegate: ItemDelegate {
     required property var modelData; required property int index
     width: ListView.view.width; height: 48
     background: Rectangle { color: parent.hovered ? "#303b3f" : "#242d32"; radius: 7 }
     contentItem: Column { RioText { text: modelData.name; color: "#e4e9eb"; font.pixelSize: 13 } RioText { text: modelData.detail; color: "#8e9ca4"; font.pixelSize: 10; elide: Text.ElideRight; width: parent.width } }
     onClicked: { bridge.selectCity(index); cityPopup.close() }
    }
    RioText { anchors.centerIn: parent; width: parent.width-20; wrapMode: Text.WordWrap; horizontalAlignment: Text.AlignHCenter; text: bridge.searchStatus || win.tr("Type a city to search","输入城市名称后搜索"); color: "#8b99a1"; visible: bridge.cityResults.length===0; font.pixelSize: 12 }
   }
   ActionButton { Layout.fillWidth: true; text: win.tr("Search","搜索"); fill: "#a7eb52"; ink: "#17210f"; enabled: !bridge.searchBusy; onClicked: bridge.searchCities(searchField.text) }
  }
 }
 Popup {
  id: consentPopup; popupType: Popup.Item; parent: Overlay.overlay; x: (win.width-width)/2; y: (win.height-height)/2; width: 366; height: 232; modal: true; focus: true; padding: 20
  background: Rectangle { color: "#1a2024"; radius: 12; border.color: "#354047" }
  ColumnLayout { anchors.fill: parent; spacing: 14
   RioText { text: win.tr("Locate your city","自动定位城市"); color: "#edf0f2"; font.pixelSize: 17 }
   RioText { Layout.fillWidth: true; Layout.fillHeight: true; wrapMode: Text.WordWrap; text: win.tr("Use ipwho.is to estimate your city from your public IP, and send approximate coordinates to Open-Meteo for weather.","使用 ipwho.is 根据公网 IP 估算城市，并将大致坐标发送给 Open-Meteo 获取天气。"); color: "#b2bdc4"; font.pixelSize: 13 }
   RowLayout { Layout.fillWidth: true; ActionButton { Layout.fillWidth: true; text: win.tr("Cancel","取消"); onClicked: consentPopup.close() } ActionButton { Layout.fillWidth: true; fill: "#a7eb52"; ink: "#17210f"; text: win.tr("Continue","继续"); onClicked: {consentPopup.close();bridge.locateCity()} } }
  }
 }
 Popup { id: notice; popupType: Popup.Item; parent: Overlay.overlay; x: (win.width-width)/2; y: (win.height-height)/2; width: 366; height: 190; modal: true; padding: 20
  background: Rectangle { color: "#1a2024"; radius: 12; border.color: "#354047" }
  ColumnLayout { anchors.fill: parent; RioText { Layout.fillWidth: true; Layout.fillHeight: true; wrapMode: Text.WordWrap; text: bridge.notice; color: "#dce3e6"; font.pixelSize: 13 } ActionButton { Layout.alignment: Qt.AlignRight; text: win.tr("OK","确定"); Layout.preferredWidth: 80; onClicked: notice.close() } }
 }
 Connections { target: bridge; function onNoticeChanged() {if(bridge.notice) notice.open()} }
}
