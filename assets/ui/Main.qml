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
 component EnglishText: RioText { font.family: "Segoe UI" }
 component SoftShadow: Item {
  property bool pressed: false
  property real cornerRadius: 8
  Rectangle { x: -1; y: 2; width: parent.width+2; height: parent.height+2; radius: parent.cornerRadius+1; color: "black"; opacity: parent.pressed ? 0.06 : 0.12 }
  Rectangle { y: 2; width: parent.width; height: parent.height; radius: parent.cornerRadius; color: "black"; opacity: parent.pressed ? 0.08 : 0.18 }
 }
 component ActionButton: Button {
  id: b
  property bool fieldStyle: false
  property color fill: fieldStyle ? "#11171b" : "#24282b"
  property color ink: "#e5e8e9"
  property bool showOutline: true
  property color hoverFill: fieldStyle || fill.a === 0 ? "#303b41" : Qt.lighter(fill,1.32)
  leftPadding: fieldStyle ? 12 : 6; rightPadding: fieldStyle ? 12 : 6
  hoverEnabled: true
  opacity: enabled ? 1 : 0.42
  implicitHeight: 38
  background: Item {
   SoftShadow { objectName: "buttonShadow"; anchors.fill: parent; pressed: b.down; visible: b.fill.a>0 || b.hovered || b.down }
   Rectangle { objectName: "buttonSurface"; anchors.fill: parent; radius: 8; color: b.down ? Qt.darker(b.hoverFill,1.18) : b.hovered ? b.hoverFill : b.fill; border.width: b.showOutline && (b.fieldStyle || b.hovered || b.activeFocus) ? 1 : 0; border.color: b.hovered || b.activeFocus ? "#a7eb52" : "#354047"; Behavior on color { ColorAnimation { duration: 100 } } }
  }
  contentItem: RioText { text: b.text; color: b.ink; font: b.font; style: Text.Raised; styleColor: "#66000000"; horizontalAlignment: b.fieldStyle ? Text.AlignLeft : Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
 }
 component ConfirmationActions: RowLayout {
  id: actions
  signal accepted()
  signal rejected()
  property string cancelObjectName: ""
  property string okObjectName: ""
  Layout.fillWidth: true; spacing: 8
  ActionButton { objectName: actions.cancelObjectName; Layout.fillWidth: true; Layout.preferredWidth: 1; Layout.minimumWidth: 0; text: win.tr("Cancel","取消"); onClicked: actions.rejected() }
  ActionButton { objectName: actions.okObjectName; Layout.fillWidth: true; Layout.preferredWidth: 1; Layout.minimumWidth: 0; text: win.tr("OK","确定"); fill: "#a7eb52"; ink: "#17210f"; onClicked: actions.accepted() }
 }
 component RefreshButton: ActionButton {
  width: 38; text: "↻"; ink: "#a7eb52"; font.pixelSize: 22
 }
 component CloseButton: ActionButton {
  id: closeButton
  width: 26; implicitHeight: 30; padding: 0; leftPadding: 0; rightPadding: 0; topPadding: 0; bottomPadding: 0
  text: "×"; fill: "transparent"; hoverFill: "#a7eb52"; ink: hovered || down ? "#17210f" : "#d0d8dd"; showOutline: false; Accessible.name: win.tr("Close","关闭")
  contentItem: Item {
   Item { anchors.fill: parent; anchors.topMargin: 1; anchors.bottomMargin: -1
    Rectangle { anchors.centerIn: parent; anchors.alignWhenCentered: false; width: 14; height: 2; rotation: 45; color: "#66000000"; antialiasing: true }
    Rectangle { anchors.centerIn: parent; anchors.alignWhenCentered: false; width: 14; height: 2; rotation: -45; color: "#66000000"; antialiasing: true }
   }
   Rectangle { objectName: "closeStrokeA"; anchors.centerIn: parent; anchors.alignWhenCentered: false; width: 14; height: 1.5; rotation: 45; color: closeButton.ink; antialiasing: true }
   Rectangle { objectName: "closeStrokeB"; anchors.centerIn: parent; anchors.alignWhenCentered: false; width: 14; height: 1.5; rotation: -45; color: closeButton.ink; antialiasing: true }
  }
 }
 component DialogPopup: Popup {
  popupType: Popup.Item; parent: Overlay.overlay; x: (win.width-width)/2; y: (win.height-height)/2
  width: 280; height: 356; modal: true; focus: true; padding: 20
  background: Rectangle { color: "#1a2024"; radius: 12; border.color: "#354047" }
  Overlay.modal: Rectangle { color: "#99080a0c" }
 }
 component FieldSurface: Item {
  property bool highlighted: false
  SoftShadow { objectName: "fieldShadow"; anchors.fill: parent; cornerRadius: 7 }
  Rectangle { anchors.fill: parent; color: "#11171b"; radius: 7; border.color: parent.highlighted ? "#a7eb52" : "#354047"; border.width: 1 }
 }
 component LanguageSelector: Slider {
  id: languageSlider
  width: 76; height: 26; padding: 2; from: 0; to: 1; stepSize: 1; snapMode: Slider.SnapAlways
  hoverEnabled: true; value: win.zh ? 0 : 1
  Accessible.name: win.tr("Language","语言")
  onMoved: bridge.setLanguage(value>=0.5 ? "en" : "zh")
  background: Item {
   SoftShadow { anchors.fill: parent; cornerRadius: 6 }
   Rectangle { id: languageTrack; anchors.fill: parent; radius: 6; color: languageSlider.hovered ? "#333b40" : "#272d30"; Behavior on color { ColorAnimation { duration: 100 } }
    gradient: Gradient {
     GradientStop { position: 0; color: Qt.darker(languageTrack.color,1.6) }
     GradientStop { position: 0.42; color: languageTrack.color }
     GradientStop { position: 1; color: Qt.lighter(languageTrack.color,1.08) }
    }
    Rectangle { x: 1; y: 1; width: parent.width-2; height: parent.height-2; radius: 5; color: "transparent"; border.width: 1; border.color: "#33000000" }
   }
  }
  handle: Item {
   z: 2
   x: languageSlider.leftPadding+languageSlider.visualPosition*(languageSlider.availableWidth-width)
   y: languageSlider.topPadding; width: 35; height: 22
   Behavior on x { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
   SoftShadow { anchors.fill: parent; cornerRadius: 4 }
   Rectangle { anchors.fill: parent; radius: 4; color: languageSlider.pressed ? "#fff07e" : languageSlider.hovered ? "#ffea61" : "#ffdf32" }
  }
  Row { anchors.fill: parent; z: 1
   Repeater { model: ["EN","CN"]; delegate: RioText { required property string modelData; width: 38; height: 26; text: modelData; color: "#a7eb52"; font.pixelSize: 10; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter } }
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
   LanguageSelector { objectName: "languageSelector"; x: 292; y: 23 }
   CloseButton { objectName: "settingsCloseButton"; x: 377; y: 20; onClicked: bridge.hideWindow() }
  }
  Rectangle { x: 20; y: 65; width: 380; height: 1; color: "#292f32" }
  Item { id: previewClip; objectName: "previewClip"; x: 20; y: 88; width: 170; height: 170; clip: true
   Image { id: screen; anchors.fill: parent; source: "image://monitor/frame?"+bridge.frameId; cache: false; smooth: true; rotation: bridge.rotation; fillMode: Image.PreserveAspectFit }
  }
  RioText { x: 212; y: 119; text: win.tr("Screen rotation","屏幕方向"); color: "#dce3e6"; font.pixelSize: 13 }
  EnglishText { x: 212; y: 147; text: Math.round(rotationSlider.value)+"°"; color: "#a7eb52"; font.pixelSize: 24; font.weight: Font.DemiBold }
  Slider {
   id: rotationSlider; objectName: "rotationSlider"; hoverEnabled: true; x: 204; y: 188; width: 194; height: 32; from: 0; to: 359; stepSize: 1; value: bridge.rotation
   onMoved: bridge.setRotation(Math.round(value))
   background: Rectangle { x: rotationSlider.leftPadding; y: rotationSlider.topPadding+rotationSlider.availableHeight/2-height/2; width: rotationSlider.availableWidth; height: 4; radius: 2; color: rotationSlider.hovered ? "#607451" : "#343d40" }
   handle: Rectangle { x: rotationSlider.leftPadding+rotationSlider.visualPosition*(rotationSlider.availableWidth-width); y: rotationSlider.topPadding+rotationSlider.availableHeight/2-height/2; width: 18; height: 18; radius: 9; color: rotationSlider.pressed || rotationSlider.hovered ? "#d1ff9b" : "#a7eb52"; border.width: rotationSlider.hovered ? 2 : 0; border.color: "#ecffd7" }
  }
  RioText { x: 212; y: 238; text: win.tr("Music appreciation","音乐欣赏模式"); color: "#dce3e6"; font.pixelSize: 13 }
  RioSwitch { objectName: "musicSwitch"; x: 358; y: 230; checked: bridge.musicEnabled; onToggled: bridge.setMusicEnabled(checked) }
  RioText { x: 24; y: 280; text: win.tr("Weather","天气"); color: "#dce3e6" }
  ActionButton { x: 20; y: 306; width: 332; text: bridge.cityLabel || win.tr("Select city","选择城市"); onClicked: { cityPopup.open(); searchField.forceActiveFocus() } }
  RefreshButton { objectName: "weatherRefreshButton"; x: 362; y: 306; onClicked: consentPopup.open() }
  RioText { x: 24; y: 365; text: win.tr("Screen content","屏幕内容"); color: "#dce3e6" }
  ActionButton { objectName: "storageButton"; x: 20; y: 390; width: 332; text: bridge.storageBusy ? bridge.storageStatus : bridge.storageError ? win.tr("Operation failed · Choose content again","操作失败 · 请重新选择内容") : bridge.storageStored ? win.tr("Stored content · Manage","屏内内容 · 管理") : win.tr("Video or image · Up to 3.4 MB","视频或图片 · 不超过 3.4 MB"); onClicked: storagePopup.open() }
  RefreshButton { objectName: "restoreDefaultButton"; x: 362; y: 390; enabled: bridge.defaultAvailable && !bridge.storageBusy; Accessible.name: win.tr("Restore default","恢复默认"); ToolTip.visible: hovered; ToolTip.text: win.tr("Restore default","恢复默认"); onClicked: bridge.requestRestoreDefault() }
  RioText { x: 24; y: 445; text: win.tr("Temperature monitoring","温度监控"); color: "#dce3e6" }
  RioText { x: 24; y: 464; width: 318; text: bridge.monitorStatus; color: "#89979f"; font.pixelSize: 10; elide: Text.ElideRight }
  RioSwitch { objectName: "monitorSwitch"; x: 358; y: 439; checked: bridge.monitorChecked; enabled: !bridge.monitorBusy && !bridge.monitorExternal; onToggled: bridge.setMonitorEnabled(checked) }
  RioText { x: 24; y: 490; text: win.tr("Start at login","登录后启动"); color: "#dce3e6" }
  RioSwitch { id: autoSwitch; objectName: "autoSwitch"; x: 358; y: 484; checked: bridge.autostart; onToggled: bridge.setAutostart(checked) }
  Rectangle { x: 20; y: 530; width: 380; height: 1; color: "#292f32" }
  EnglishText { x: 24; y: 561; text: "Your system. At a glance."; color: "#899398"; font.pixelSize: 10 }
  Row {
   id: temperatureLoading; objectName: "temperatureLoading"; x: (parent.width-width)/2; y: 563; spacing: 7; visible: bridge.monitorBusy || bridge.storageBusy
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
 DialogPopup {
  id: musicPopup; objectName: "musicPopup"; height: 410
  ColumnLayout { anchors.fill: parent; spacing: 12
   RowLayout { Layout.fillWidth: true; RioText { text: win.tr("Music settings","音乐设置"); font.pixelSize: 17; color: "#edf0f2"; Layout.fillWidth: true } CloseButton { onClicked: musicPopup.close() } }
   RioText { Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 11; color: "#a6b7b0"; text: win.tr("Analyzes speaker audio locally. No microphone, recording files or audio uploads. Other apps' sounds may be included.","仅在本机分析输出声音，不使用麦克风，不保存或上传音频；可能包含其他应用声音。") }
   ComboBox { id: sourceChoice; Layout.fillWidth: true; implicitHeight: 36;
    background: Rectangle { color: "#11171b"; radius: 7; border.color: "#354047" }
    contentItem: RioText { text: sourceChoice.displayText; color: "#e5e8e9"; verticalAlignment: Text.AlignVCenter; leftPadding: 10; rightPadding: 24; elide: Text.ElideRight; font.pixelSize: 12 }
    indicator: RioText { x: sourceChoice.width-22; y: 8; text: "▾"; color: "#a7eb52" }
    delegate: ItemDelegate { width: sourceChoice.width; contentItem: RioText { text: modelData.label; color: "#e5e8e9"; elide: Text.ElideRight } background: Rectangle { color: highlighted ? "#354331" : "#1a2024" } }
    popup: Popup { y: sourceChoice.height; width: sourceChoice.width; padding: 2; background: Rectangle { color: "#1a2024"; radius: 6; border.color: "#354047" } contentItem: ListView { implicitHeight: Math.min(contentHeight,160); clip: true; model: sourceChoice.popup.visible ? sourceChoice.delegateModel : null; currentIndex: sourceChoice.highlightedIndex } }
 model: bridge.musicSources; textRole: "label"; valueRole: "id"; onActivated: bridge.setMusicSource(currentValue); Component.onCompleted: currentIndex=indexOfValue(bridge.musicSource) }
   RowLayout { Layout.fillWidth: true; RioText { text: win.tr("Online lyrics","在线歌词"); color: "#edf0f2"; Layout.fillWidth: true } RioSwitch { id: lyricsToggle; checked: bridge.musicOnline; onToggled: { if(checked) lyricsConsent.open(); else bridge.setMusicOnline(false) } } }
   ActionButton { Layout.fillWidth: true; text: win.tr("Import LRC for current song","为当前歌曲导入 LRC"); onClicked: bridge.importMusicLyrics() }
   RioText { Layout.fillWidth: true; Layout.fillHeight: true; wrapMode: Text.WrapAnywhere; font.pixelSize: 10; color: "#8c9c95"; text: bridge.musicStatus }
  }
 }
 DialogPopup {
  id: lyricsConsent; height: 278
  onClosed: lyricsToggle.checked=Qt.binding(function(){return bridge.musicOnline})
  ColumnLayout { anchors.fill: parent; spacing: 12
   RioText { text: win.tr("Online lyric matching","在线歌词匹配"); font.pixelSize: 17; color: "#edf0f2" }
   RioText { Layout.fillWidth: true; Layout.fillHeight: true; wrapMode: Text.WordWrap; font.pixelSize: 12; color: "#b2bdc4"; text: win.tr("Match lyrics with QQ Music or NetEase for recognized players, then LRCLIB.net as fallback. Song metadata is sent to these services; never audio or account credentials. Unofficial platform interfaces may stop working.","识别到 QQ 音乐或网易云时，先向对应平台查询歌词，再用 LRCLIB.net 兜底。会发送歌曲信息，不发送音频或账号凭据。平台非公开接口可能失效，不保证匹配成功。") }
   ConfirmationActions { onRejected: { bridge.setMusicOnline(false); lyricsConsent.close() } onAccepted: { bridge.setMusicOnline(true); lyricsConsent.close() } }
  }
 }
 DialogPopup {
  id: storagePopup; objectName: "storagePopup"
  onOpened: { bridge.prepareStoragePreview(); storageFileButton.forceActiveFocus() }
  closePolicy: bridge.storageWriting ? Popup.NoAutoClose : Popup.CloseOnEscape | Popup.CloseOnPressOutside
  ColumnLayout {
   anchors.fill: parent; spacing: 14
   RowLayout { Layout.fillWidth: true; RioText { text: win.tr("Screen content","屏幕内容"); color: "#edf0f2"; font.pixelSize: 17; Layout.fillWidth: true } CloseButton { objectName: "storageCloseButton"; Layout.preferredWidth: 26; enabled: !bridge.storageWriting; onClicked: storagePopup.close() } }
   ActionButton {
    id: storageFileButton; objectName: "chooseStorageButton"; Layout.fillWidth: true; implicitHeight: 40; fieldStyle: true
    text: win.tr("Choose file","选择文件"); enabled: !bridge.storageBusy; onClicked: bridge.chooseStorageFile()
   }
   Item {
    id: storagePreviewArea; Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 80; clip: true
    property real previewSide: Math.min(128,Math.max(48,height-storageFilename.implicitHeight-storageFileInfo.implicitHeight-8))
    Column {
     anchors.centerIn: parent; width: parent.width; spacing: 4
     Item { anchors.horizontalCenter: parent.horizontalCenter; width: storagePreviewArea.previewSide; height: width
      AnimatedImage { anchors.fill: parent; source: bridge.storagePreview; playing: storagePopup.visible; fillMode: Image.PreserveAspectFit; visible: source.toString() !== "" }
      RioText { anchors.centerIn: parent; width: parent.width; wrapMode: Text.WordWrap; text: win.tr("Stored preview unavailable","暂无屏内内容预览"); color: "#819099"; horizontalAlignment: Text.AlignHCenter; visible: bridge.storagePreview === "" }
     }
     EnglishText { id: storageFilename; width: parent.width; text: bridge.storageName; color: "#edf0f2"; font.pixelSize: 12; horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight }
     EnglishText { id: storageFileInfo; width: parent.width; text: bridge.storageDetail; color: "#91a0a9"; font.pixelSize: 10; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap }
    }
   }
   ProgressBar { visible: bridge.storageWriting; Layout.fillWidth: true; from: 0; to: 1; value: bridge.storageProgress
    background: Rectangle { implicitHeight: 4; color: "#354047"; radius: 2 }
    contentItem: Item { implicitHeight: 4; Rectangle { width: parent.width*(bridge.storageBusy && !bridge.storageWriting ? 0.3 : bridge.storageProgress); height: 4; radius: 2; color: "#a7eb52" } }
   }
   ActionButton { objectName: "writeStorageButton"; Layout.fillWidth: true; text: bridge.storageWriting ? Math.round(bridge.storageProgress*100)+"%" : win.tr("Write","写入"); fill: "#a7eb52"; ink: "#17210f"; enabled: bridge.storageReady && !bridge.storageBusy; onClicked: bridge.writeStorage() }
  }
 }
 DialogPopup {
  id: resetConfirmation; objectName: "resetConfirmation"; height: 136; visible: bridge.defaultConfirmation
  onClosed: if(bridge.defaultConfirmation) bridge.confirmRestoreDefault(false)
  ColumnLayout { anchors.fill: parent; spacing: 12
   RioText { Layout.fillWidth: true; Layout.fillHeight: true; verticalAlignment: Text.AlignVCenter; text: win.tr("Restore default?","恢复默认动画？"); color: "#edf0f2"; font.pixelSize: 16 }
   ConfirmationActions { cancelObjectName: "cancelDefaultButton"; okObjectName: "confirmDefaultButton"; onRejected: bridge.confirmRestoreDefault(false); onAccepted: bridge.confirmRestoreDefault(true) }
  }
 }
 DialogPopup {
  id: cityPopup; objectName: "cityPopup"
  ColumnLayout {
   anchors.fill: parent; spacing: 14
   RowLayout { Layout.fillWidth: true; RioText { text: win.tr("Choose your city","选择城市"); color: "#edf0f2"; font.pixelSize: 17; Layout.fillWidth: true } CloseButton { objectName: "cityCloseButton"; Layout.preferredWidth: 26; onClicked: cityPopup.close() } }
   TextField {
    id: searchField; objectName: "searchField"; Layout.fillWidth: true; implicitHeight: 40; placeholderText: win.tr("Search city or region","搜索城市或地区"); color: "#edf0f2"; placeholderTextColor: "#7f8d95"; selectByMouse: true; leftPadding: 12; font.pixelSize: 13
    background: FieldSurface { highlighted: searchField.activeFocus || searchField.hovered }
    onAccepted: bridge.searchCities(text)
   }
   ListView {
    Layout.fillWidth: true; Layout.fillHeight: true; clip: true; spacing: 5; model: bridge.cityResults
    delegate: ActionButton {
     required property var modelData; required property int index
     width: ListView.view.width; height: 48; text: modelData.name
     contentItem: Column { RioText { text: modelData.name; color: "#e4e9eb"; font.pixelSize: 13 } RioText { text: modelData.detail; color: "#8e9ca4"; font.pixelSize: 10; elide: Text.ElideRight; width: parent.width } }
     onClicked: { bridge.selectCity(index); cityPopup.close() }
    }
    RioText { anchors.centerIn: parent; width: parent.width-20; wrapMode: Text.WordWrap; horizontalAlignment: Text.AlignHCenter; text: bridge.searchStatus || win.tr("Type a city to search","输入城市名称后搜索"); color: "#8b99a1"; visible: bridge.cityResults.length===0; font.pixelSize: 12 }
   }
   ActionButton { Layout.fillWidth: true; text: win.tr("Search","搜索"); fill: "#a7eb52"; ink: "#17210f"; enabled: !bridge.searchBusy; onClicked: bridge.searchCities(searchField.text) }
  }
 }
 DialogPopup {
  id: consentPopup; objectName: "consentPopup"; height: 232
  ColumnLayout { anchors.fill: parent; spacing: 14
   RioText { text: win.tr("Locate your city","自动定位城市"); color: "#edf0f2"; font.pixelSize: 17 }
   RioText { Layout.fillWidth: true; Layout.fillHeight: true; wrapMode: Text.WordWrap; text: win.tr("Use ipwho.is to estimate your city from your public IP, and send approximate coordinates to Open-Meteo for weather.","使用 ipwho.is 根据公网 IP 估算城市，并将大致坐标发送给 Open-Meteo 获取天气。"); color: "#b2bdc4"; font.pixelSize: 13 }
   ConfirmationActions { cancelObjectName: "cancelLocateButton"; okObjectName: "confirmLocateButton"; onRejected: consentPopup.close(); onAccepted: { consentPopup.close(); bridge.locateCity() } }
  }
 }
 Popup { id: notice; popupType: Popup.Item; parent: Overlay.overlay; x: (win.width-width)/2; y: (win.height-height)/2; width: 366; height: 190; modal: true; padding: 20
  background: Rectangle { color: "#1a2024"; radius: 12; border.color: "#354047" }
  ColumnLayout { anchors.fill: parent; RioText { Layout.fillWidth: true; Layout.fillHeight: true; wrapMode: Text.WordWrap; text: bridge.notice; color: "#dce3e6"; font.pixelSize: 13 } ActionButton { Layout.alignment: Qt.AlignRight; text: win.tr("OK","确定"); Layout.preferredWidth: 80; onClicked: notice.close() } }
 }
 Connections { target: bridge; function onNoticeChanged() {if(bridge.notice) notice.open()} }
}

