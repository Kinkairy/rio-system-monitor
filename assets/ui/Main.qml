import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
 id: win
 width: 448; height: 630; visible: true; color: "transparent"
 flags: Qt.Window | Qt.FramelessWindowHint
 title: "RIO System Monitor"
 property bool zh: bridge.language === "zh"
 function tr(en, cn) { return zh ? cn : en }
 onClosing: function(close) { close.accepted = false; bridge.hideWindow() }
 onVisibleChanged: bridge.setPreviewVisible(visible)
 font.family: win.zh ? "Microsoft YaHei UI" : "Segoe UI"
 font.pixelSize: 13
 component RioText: Text { font.family: win.zh ? "Microsoft YaHei UI" : "Segoe UI" }
 component ActionButton: Button {
  id: b
  property color fill: "#24282b"
  property color ink: "#e5e8e9"
  property bool showOutline: true
  property color hoverFill: fill.a === 0 ? "#303b41" : Qt.lighter(fill,1.32)
  hoverEnabled: true
  implicitHeight: 38
  background: Item {
   Rectangle { x: -1; y: 2; width: parent.width+2; height: parent.height+2; radius: 9; color: "#000000"; opacity: b.down ? 0.06 : 0.12; visible: b.fill.a>0 || b.hovered || b.down }
   Rectangle { y: 2; width: parent.width; height: parent.height; radius: 8; color: "#000000"; opacity: b.down ? 0.08 : 0.18; visible: b.fill.a>0 || b.hovered || b.down }
   Rectangle { objectName: "buttonSurface"; anchors.fill: parent; radius: 8; color: b.down ? Qt.darker(b.hoverFill,1.18) : b.hovered ? b.hoverFill : b.fill; border.width: b.showOutline && (b.hovered || b.activeFocus) ? 1 : 0; border.color: "#a7eb52"; Behavior on color { ColorAnimation { duration: 100 } } }
  }
  contentItem: RioText { text: b.text; color: b.ink; font: b.font; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
 }
 component RefreshButton: ActionButton {
  width: 38; text: "↻"; ink: "#a7eb52"; font.pixelSize: 22
 }
 component CloseButton: ActionButton {
  id: closeButton
  width: 26; implicitHeight: 30; padding: 0; leftPadding: 0; rightPadding: 0; topPadding: 0; bottomPadding: 0
  text: "×"; fill: "transparent"; hoverFill: "#a7eb52"; ink: hovered || down ? "#17210f" : "#d0d8dd"; showOutline: false; Accessible.name: win.tr("Close","关闭")
  contentItem: Item {
   Rectangle { anchors.centerIn: parent; anchors.alignWhenCentered: false; width: 14; height: 1.5; rotation: 45; color: closeButton.ink; antialiasing: true }
   Rectangle { anchors.centerIn: parent; anchors.alignWhenCentered: false; width: 14; height: 1.5; rotation: -45; color: closeButton.ink; antialiasing: true }
  }
 }
 component RioSwitch: Switch {
  id: sw
  hoverEnabled: true
  implicitWidth: 42; implicitHeight: 24
  indicator: Rectangle {
   id: switchTrack
   width: 42; height: 24; radius: 12; color: !sw.enabled ? "#343a3e" : sw.pressed ? "#d1ff9b" : sw.hovered ? "#c4ff7b" : sw.checked ? "#a7eb52" : "#343a3e"; border.width: sw.enabled && (sw.hovered || sw.activeFocus) ? 1 : 0; border.color: "#d1ff9b"
   gradient: Gradient {
    GradientStop { position: 0; color: Qt.darker(switchTrack.color,1.2) }
    GradientStop { position: 0.38; color: switchTrack.color }
    GradientStop { position: 1; color: Qt.lighter(switchTrack.color,1.04) }
   }
   Behavior on color { ColorAnimation { duration: 130 } }
   Rectangle { x: 1; y: 1; width: parent.width-2; height: parent.height-2; radius: 11; color: "transparent"; border.width: 1; border.color: "#24000000" }
   Rectangle { width: 18; height: 18; y: 5; x: switchThumb.x; radius: 9; color: "#000000"; opacity: sw.enabled ? 0.22 : 0.1 }
   Rectangle { id: switchThumb; width: 18; height: 18; y: 3; x: sw.checked ? 21 : 3; radius: 9; color: !sw.enabled ? "#7b8489" : sw.checked || sw.hovered || sw.pressed ? "#18200e" : "#a4acb0"; Behavior on x { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } } }
  }
 }
 // A soft shadow inside the same transparent native window. No system frame or second window.
 Repeater {
  model: 12
  Rectangle { x: 14-index; y: 16-index; width: 420+index*2; height: 600+index*2; radius: 12+index; color: "black"; opacity: (12-index)*0.0024 }
 }
 Rectangle {
  id: panel; x: 14; y: 12; width: 420; height: 602; radius: 12; color: "#111416"
  Item {
   x: 0; y: 0; width: parent.width; height: 66
   DragHandler { target: null; onActiveChanged: if(active) win.startSystemMove() }
   Image { x: 20; y: 22; width: 76; height: 25; source: "../rio-brand.png"; fillMode: Image.PreserveAspectFit; sourceClipRect: Qt.rect(8,88,240,80) }
   RioText { x: 109; y: 24; text: win.tr("Settings","设置"); color: "#e9edef"; font.pixelSize: 17 }
   Rectangle {
    x: 292; y: 23; width: 76; height: 26; radius: 6; color: "#272d30"
    Rectangle { x: win.zh ? 39 : 2; y: 2; width: 35; height: 22; radius: 4; color: "#ffdf32"; Behavior on x { NumberAnimation { duration: 140 } } }
    Row { anchors.fill: parent; Repeater { model: ["EN","CN"]; delegate: ActionButton { required property string modelData; required property int index; width: 38; height: 26; text: modelData; fill: "transparent"; showOutline: false; hoverFill: (win.zh === (index===1)) ? "#ffed7c" : "#414c52"; ink: (win.zh === (index===1)) ? "#161a10" : "#d0d8dd"; font.pixelSize: 10; onClicked: bridge.setLanguage(index===1 ? "zh":"en") } } }
   }
   CloseButton { objectName: "settingsCloseButton"; x: 377; y: 20; onClicked: bridge.hideWindow() }
  }
  Rectangle { x: 20; y: 65; width: 380; height: 1; color: "#292f32" }
  Item { id: previewClip; objectName: "previewClip"; x: 20; y: 88; width: 170; height: 170; clip: true
   Image { id: screen; anchors.fill: parent; source: "image://monitor/frame?"+bridge.frameId; cache: false; smooth: true; rotation: bridge.rotation; fillMode: Image.PreserveAspectFit }
  }
  RioText { x: 212; y: 119; text: win.tr("Screen rotation","屏幕方向"); color: "#dce3e6"; font.pixelSize: 13 }
  RioText { x: 212; y: 147; text: Math.round(rotationSlider.value)+"°"; color: "#a7eb52"; font.pixelSize: 24; font.weight: Font.DemiBold }
  Slider {
   id: rotationSlider; objectName: "rotationSlider"; hoverEnabled: true; x: 204; y: 188; width: 194; height: 32; from: 0; to: 359; stepSize: 1; value: bridge.rotation
   onMoved: bridge.setRotation(Math.round(value))
   background: Rectangle { x: rotationSlider.leftPadding; y: rotationSlider.topPadding+rotationSlider.availableHeight/2-height/2; width: rotationSlider.availableWidth; height: 4; radius: 2; color: rotationSlider.hovered ? "#607451" : "#343d40" }
   handle: Rectangle { x: rotationSlider.leftPadding+rotationSlider.visualPosition*(rotationSlider.availableWidth-width); y: rotationSlider.topPadding+rotationSlider.availableHeight/2-height/2; width: 18; height: 18; radius: 9; color: rotationSlider.pressed || rotationSlider.hovered ? "#d1ff9b" : "#a7eb52"; border.width: rotationSlider.hovered ? 2 : 0; border.color: "#ecffd7" }
  }
  RioText { x: 24; y: 280; text: win.tr("Weather","天气"); color: "#dce3e6" }
  ActionButton { x: 20; y: 306; width: 332; text: bridge.cityLabel || win.tr("Select city","选择城市"); onClicked: { cityPopup.open(); searchField.forceActiveFocus() } }
  RefreshButton { objectName: "weatherRefreshButton"; x: 362; y: 306; onClicked: consentPopup.open() }
  RioText { x: 24; y: 365; text: win.tr("Screen content","屏幕内容"); color: "#dce3e6" }
  ActionButton { objectName: "storageButton"; x: 20; y: 390; width: 332; text: bridge.storageStored ? win.tr("Stored content · Manage","屏内内容 · 管理") : win.tr("Video or image · Up to 3.4 MB","视频或图片 · 不超过 3.4 MB"); onClicked: storagePopup.open() }
  RefreshButton { objectName: "restoreDefaultButton"; x: 362; y: 390; enabled: bridge.defaultAvailable && !bridge.storageBusy; Accessible.name: win.tr("Restore default","恢复默认"); ToolTip.visible: hovered; ToolTip.text: win.tr("Restore default","恢复默认"); onClicked: bridge.requestRestoreDefault() }
  RioText { x: 24; y: 445; text: win.tr("Temperature monitoring","温度监控"); color: "#dce3e6" }
  RioText { x: 24; y: 464; width: 318; text: bridge.monitorStatus; color: "#89979f"; font.pixelSize: 10; elide: Text.ElideRight }
  RioSwitch { objectName: "monitorSwitch"; x: 358; y: 439; checked: bridge.monitorChecked; enabled: !bridge.monitorBusy && !bridge.monitorExternal; onToggled: bridge.setMonitorEnabled(checked) }
  RioText { x: 24; y: 490; text: win.tr("Start at login","登录后自动启动"); color: "#dce3e6" }
  RioSwitch { id: autoSwitch; objectName: "autoSwitch"; x: 358; y: 484; checked: bridge.autostart; onToggled: bridge.setAutostart(checked) }
  Rectangle { x: 20; y: 530; width: 380; height: 1; color: "#292f32" }
  RioText { x: 24; y: 561; text: "Your system. At a glance."; color: "#899398"; font.pixelSize: 10 }
  Row {
   id: temperatureLoading; objectName: "temperatureLoading"; x: (parent.width-width)/2; y: 563; spacing: 7; visible: bridge.monitorBusy
   Repeater {
    model: 3
    delegate: Rectangle {
     id: loadingDot; required property int index; objectName: "temperatureLoadingDot"+index
     width: 6; height: 6; radius: 3; color: "#a7eb52"; opacity: 0.25
     SequentialAnimation on opacity {
      running: temperatureLoading.visible && win.visible; loops: Animation.Infinite
      PauseAnimation { duration: loadingDot.index*150 }
      NumberAnimation { from: 0.25; to: 1; duration: 200; easing.type: Easing.InOutQuad }
      NumberAnimation { from: 1; to: 0.25; duration: 200; easing.type: Easing.InOutQuad }
      PauseAnimation { duration: 650-loadingDot.index*150 }
     }
    }
   }
  }
  ActionButton { objectName: "saveButton"; x: 310; y: 549; width: 90; height: 34; text: win.tr("Save","保存"); fill: "#a7eb52"; ink: "#17210f"; onClicked: bridge.saveAndHide() }
 }
 Popup {
  id: storagePopup; objectName: "storagePopup"; popupType: Popup.Item; parent: Overlay.overlay; x: (win.width-width)/2; y: (win.height-height)/2; width: 232; height: 294+(bridge.storageBusy || bridge.storageError ? 34 : 0)+(bridge.storageWriting ? 12 : 0); modal: true; focus: true; padding: 18
  closePolicy: bridge.storageWriting ? Popup.NoAutoClose : Popup.CloseOnEscape | Popup.CloseOnPressOutside
  background: Rectangle { color: "#1a2024"; radius: 12; border.color: "#354047" }
  Overlay.modal: Rectangle { color: "#99080a0c" }
  ColumnLayout {
   anchors.fill: parent; spacing: 8
   RowLayout { Layout.fillWidth: true; RioText { text: win.tr("Screen content","屏幕内容"); color: "#edf0f2"; font.pixelSize: 17; Layout.fillWidth: true } CloseButton { objectName: "storageCloseButton"; Layout.preferredWidth: 26; enabled: !bridge.storageWriting; onClicked: storagePopup.close() } }
   Item { Layout.fillWidth: true; Layout.preferredHeight: 120; Layout.maximumHeight: 120
    AnimatedImage { anchors.centerIn: parent; width: 120; height: 120; source: bridge.storagePreview; playing: storagePopup.visible; fillMode: Image.PreserveAspectFit; visible: source.toString() !== "" }
    RioText { anchors.centerIn: parent; width: parent.width; text: win.tr("Preview your video or image","预览视频或图片"); color: "#819099"; horizontalAlignment: Text.AlignHCenter; visible: bridge.storagePreview === "" }
   }
   RioText { Layout.fillWidth: true; Layout.minimumWidth: 0; text: bridge.storageName || win.tr("No file selected","尚未选择文件"); color: "#edf0f2"; font.pixelSize: 12; horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight }
   RioText { Layout.fillWidth: true; Layout.minimumWidth: 0; text: bridge.storageDetail || win.tr("Up to 3.4 MB · Fits 480 × 480 · No audio","不超过 3.4 MB · 自动适配 480 × 480 · 无声"); color: "#91a0a9"; font.pixelSize: 10; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap }
   RioText { visible: bridge.storageBusy || bridge.storageError; Layout.fillWidth: true; Layout.preferredHeight: 26; wrapMode: Text.WordWrap; text: bridge.storageStatus; color: "#d4e0e5"; font.pixelSize: 11 }
   ProgressBar { visible: bridge.storageWriting; Layout.fillWidth: true; from: 0; to: 1; value: bridge.storageProgress
    background: Rectangle { implicitHeight: 4; color: "#354047"; radius: 2 }
    contentItem: Item { implicitHeight: 4; Rectangle { width: parent.width*(bridge.storageBusy && !bridge.storageWriting ? 0.3 : bridge.storageProgress); height: 4; radius: 2; color: "#a7eb52" } }
   }
   RowLayout { Layout.fillWidth: true; spacing: 8
    ActionButton { objectName: "chooseStorageButton"; Layout.fillWidth: true; text: win.tr("Choose file","选择文件"); enabled: !bridge.storageBusy; onClicked: bridge.chooseStorageFile() }
    ActionButton { objectName: "writeStorageButton"; Layout.fillWidth: true; text: bridge.storageWriting ? Math.round(bridge.storageProgress*100)+"%" : win.tr("Write","写入"); fill: "#a7eb52"; ink: "#17210f"; enabled: bridge.storageReady && !bridge.storageBusy; onClicked: bridge.writeStorage() }
   }
  }
 }
 Popup {
  id: resetConfirmation; objectName: "resetConfirmation"; popupType: Popup.Item; parent: Overlay.overlay; x: (win.width-width)/2; y: (win.height-height)/2; width: 232; height: 136; modal: true; focus: true; padding: 18; visible: bridge.defaultConfirmation
  onClosed: if(bridge.defaultConfirmation) bridge.confirmRestoreDefault(false)
  background: Rectangle { color: "#1a2024"; radius: 12; border.color: "#354047" }
  Overlay.modal: Rectangle { color: "#99080a0c" }
  ColumnLayout { anchors.fill: parent; spacing: 12
   RioText { Layout.fillWidth: true; Layout.fillHeight: true; verticalAlignment: Text.AlignVCenter; text: win.tr("Restore default?","恢复默认动画？"); color: "#edf0f2"; font.pixelSize: 16 }
   RowLayout { Layout.fillWidth: true; spacing: 8
    ActionButton { objectName: "cancelDefaultButton"; Layout.fillWidth: true; text: win.tr("Cancel","取消"); onClicked: bridge.confirmRestoreDefault(false) }
    ActionButton { objectName: "confirmDefaultButton"; Layout.fillWidth: true; text: win.tr("OK","确定"); fill: "#a7eb52"; ink: "#17210f"; onClicked: { bridge.confirmRestoreDefault(true); storagePopup.open() } }
   }
  }
 }
 Popup {
  id: cityPopup; popupType: Popup.Item; objectName: "cityPopup"; parent: Overlay.overlay; x: (win.width-width)/2; y: (win.height-height)/2; width: 376; height: 356; modal: true; focus: true; padding: 20
  background: Rectangle { color: "#1a2024"; radius: 12; border.color: "#354047" }
  Overlay.modal: Rectangle { color: "#99080a0c" }
  ColumnLayout {
   anchors.fill: parent; spacing: 14
   RowLayout { Layout.fillWidth: true; RioText { text: win.tr("Choose your city","选择城市"); color: "#edf0f2"; font.pixelSize: 17; Layout.fillWidth: true } CloseButton { objectName: "cityCloseButton"; Layout.preferredWidth: 26; onClicked: cityPopup.close() } }
   TextField {
    id: searchField; objectName: "searchField"; Layout.fillWidth: true; implicitHeight: 40; placeholderText: win.tr("Search city or region","搜索城市或地区"); color: "#edf0f2"; placeholderTextColor: "#7f8d95"; selectByMouse: true; leftPadding: 12; font.pixelSize: 13
    background: Rectangle { color: "#11171b"; radius: 7; border.color: searchField.activeFocus ? "#a7eb52" : "#354047"; border.width: 1 }
    onAccepted: bridge.searchCities(text)
   }
   ListView {
    Layout.fillWidth: true; Layout.fillHeight: true; clip: true; spacing: 5; model: bridge.cityResults
    delegate: ItemDelegate {
     hoverEnabled: true
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
