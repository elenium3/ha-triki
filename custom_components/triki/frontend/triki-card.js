// custom:triki-card: a live 3D view of a Żabka Triki token, part of the Triki integration.
//
// Data: the integration's websocket command triki/subscribe sends `status` (link, battery,
// RSSI, rate), `motion` (pose quaternion in the sensor frame, roll/pitch/yaw, the last gyro
// and accelerometer reading) at up to 30 per second while the token streams, and `event`
// (gestures). Nothing of this goes through entity states.
//
// Frames: the pose quaternion turns sensor vectors into a world frame with z up. The sensor
// has +z out of the resin side, +x to the left of the PCB art and -y towards its top
// (docs/protocol.md). The scene keeps that world frame in a group turned to three.js's Y-up
// (and half a turn about z, so the art faces the camera upright at heading 0); the model sits
// in the sensor frame inside a pivot that takes the quaternion as is.
//
// Models: `cap` (default) is procedural, built from calipered dimensions (triki-cap.js);
// `glb` is Flopsstuff's textured model (MIT, triki.glb). Renderer: three.js (MIT), bundled
// as triki-three.js. All of it is loaded only when a card is on screen.

const BASE = new URL(".", import.meta.url).href;
const VERSION = new URL(import.meta.url).searchParams.get("v") || "";
const asset = (name) => `${BASE}${name}${VERSION ? `?v=${VERSION}` : ""}`;

// The card's buttons, as named in its `buttons` option.
const BUTTONS = ["calibrate", "align", "led", "check"];
// status chips; "state" also carries the chip of a check open elsewhere
const CHIPS = ["state", "rate", "signal", "battery", "link"];

/** The card's texts in the user's language (profile, then server), else English. */
function cardStrings(hass) {
  return STRINGS[(hass.locale?.language || hass.language || "en").slice(0, 2)] || STRINGS.en;
}

/** The card config with its defaults filled in. */
export function cardConfig(config) {
  const c = { show_values: true, show_history: true, show_controls: true, show_model: true, show_status: true, show_gestures: true, ...config };
  // show_controls: false is the old way to hide every button and the help
  c.buttons = Array.isArray(c.buttons) ? c.buttons : (c.show_controls ? [...BUTTONS] : []);
  c.show_help ??= !!c.show_controls;
  // show_status: false is the old way to hide every chip
  c.chips = Array.isArray(c.chips) ? c.chips : (c.show_status === false ? [] : [...CHIPS]);
  return c;
}

// the gesture list: [item, events that light it, option that turns it on]
const GESTURES = [
  ["press", ["press", "single_press"], null], ["double_press", ["double_press"], "multi_press"],
  ["triple_press", ["triple_press"], "multi_press"], ["long_press", ["long_press"], null],
  ["knob", ["rotate_cw", "rotate_ccw"], "knob"], ["tilt", ["tilt_left", "tilt_right"], "tilt"],
  ["shake", ["shake"], "shake"], ["flip", ["flip"], "motion_gestures"],
  ["tap", ["tap", "double_tap"], "motion_gestures"], ["throw", ["throw"], "motion_gestures"],
];

const STRINGS = {
  en: {
    auto: "Auto", asleep: "Asleep", dozing: "Dozing off",
    dozeHint: "Dropped after idle. Presses won't register for ~{n} s more, and each one restarts the 3-minute wait: put the cap down and leave it",
    dozeLate: "Dropped after idle. Presses won't register until it falls asleep, and each one restarts the 3-minute wait: put the cap down and leave it", connected: "Connected", streaming: "Live", unresponsive: "Not responding",
    wake: "Press the cap to wake it", heading: "Direction unknown after a restart: lay the cap dot away from you and press Align direction.", gyro: "Gyroscope, °/s", accel: "Accelerometer, g",
    roll: "Left-right", pitch: "Forward-back", yaw: "Turn", reset: "Align direction", led: "LED", calibrate: "Calibrate",
    editor: { title: "Title", model: "Model style", show_model: "3D model and angles", chips: "Status chips", show_values: "Gyro and accelerometer bars",
      show_history: "Last 10 s graph", show_gestures: "Gesture list", buttons: "Buttons", show_help: "Help under the buttons",
      show_controls: "Buttons and help (legacy)", admin: "Only admins see Calibrate and Check.",
      opt: { state: "State", rate: "Rate", signal: "Signal, dBm", battery: "Battery", link: "Frames received, %", cap: "Triki (built-in)", glb: "Flopsstuff (textured)" } },
    help: { mark: "The yellow stripe on the model marks the edge with the dot above the Z (circled in the photo), so you can tell which way the model is turned.", cal: "<b>Calibrate</b> once per cap. Lay it on the table, dot away from you, so the model learns what level means for this cap, then match the logo. It's saved for good.", align: "<b>Align direction</b> now and then. The cap feels tilt through gravity, but it has no compass, so it can't tell which way it's turned. The gyroscope tracks turns but slowly drifts, and a Home Assistant restart loses the direction. If the stripe on the model isn't on the same edge as the dot on the cap, lay the cap dot away from you and press this button. Calibration is kept.",
      led: "<b>LED</b> turns the cap's green light on and off. The cap can't report the light, so the button is lit only after you turn it on, until the cap dozes off. It drains the coin cell: keep it off unless you need it.",
      check: "<b>Check</b> walks you through the link, the knob, the button and every gesture you've turned on, then suggests option changes. It takes a few minutes, and you can skip any step. Run it after setup or whenever a gesture misfires." },
    cal: { find: "Find the dot above the Z on the green side (circled in the photo). On the model, that edge has the yellow stripe.", flat: "Lay the cap on the table, either side up, with that edge away from you. Let go and press Done.", heading: "Lay the cap on the table, that edge away from you, and press Done. The stripe on the model moves to the far edge too.", turned: "Direction aligned", logo: "Now the logo (once per cap: it's crimped on at any angle). Lay the cap green side up with the Z upright and the dot on top, then flip it over its right edge. Turn the logo below with the slider until it matches your cap.", resin: "Green side", metal: "After the flip", next: "Done", cancel: "Cancel", skip: "Skip", saved: "Calibrated",
      err: { moving: "It's moving: hold still for a second", not_flat: "It's not lying flat", asleep: "The cap is asleep: wake it first", no_data: "No data yet: wake the cap" } },
    glist: { title: "What the cap can do", hint: "Tap a name to see how. It lights up when the cap does it.", off: "turned off in the integration options",
      knob: "Knob ↻ ↺", tilt: "Tilt ← →", how: { press: "Press the whole cap.", double_press: "Two quick presses.", triple_press: "Three quick presses.",
        long_press: "Press and hold.", knob: "Turn it flat on the table, like a knob.", tilt: "Hold it in your hand and lean it right or left.",
        shake: "Shake it sharply a few times.", flip: "Flip it onto the other side.", tap: "Tap the table next to it with a finger.", throw: "Toss it up and catch it." } },
    button: "Button", rate: "Hz", linkq: "Frames received this session", history: "Last 10 s", nodevice: "No Triki cap found",
    check: { title: "Check", open: "Check",
      steps: { rest: "Lying still", flat: "Starting position", tilt: "Tilt", turn_cw: "Knob clockwise", turn_ccw: "Knob counter-clockwise", handle: "Pick up and put down", lean: "Lean in the hand", press: "Button", flip: "Flip", tap: "Tap", shake: "Shake", throw: "Toss", drift: "Direction drift", sleep: "Sleep and wake" },
      text: {
        identify: "Pick the cap below, or just press it.",
        wake: "Press the cap to wake it.",
        rest: "Put the cap on the table and leave it alone for 10 seconds. This measures the link and the sensor noise.",
        flat: "Lay the cap on the table, dot away from you, let go and press Done. Tilts and turns are measured from here, and it's saved as the cap's calibration too.",
        tilt: "Lift the dot edge about 1 cm (a fingertip) and hold it for a second. The model should tilt like the faint hint.",
        turn_cw: "Turn the cap a quarter turn clockwise on the table: the stripe moves from the far edge to the right. Let go, regrip and turn another quarter. Then press Done.",
        turn_ccw: "Now the same counter-clockwise: two quarter turns, letting go in between. Then press Done.",
        knobOff: "The knob is off in the options, so this step only checks that the model turns with the cap.",
        lean: "Hold the cap level in your hand, dot edge towards you. Lean it right about 30° until Tilt → shows, then level it; lean it left, then level it. Do this three times.",
        tap: "Tap the table next to the cap with a finger 2–3 times, a second apart.",
        shake: "Take the cap in your hand and shake it 3 times, a couple of seconds apart, just as you will in real use.",
        handle: "Pick the cap up the way you would before a gesture, hold it and put it back. Do it 5 times, a bit differently each time. Don't turn or lean it on purpose: anything that fires is a false alarm. A pick-up counts once the cap lies still on the table again.",
        sleep: "Put the cap down and leave it. Home Assistant now drops the link as if after idle: for about 3 minutes the cap dozes off and presses won't register. When this says Asleep, press the cap once. You can skip this step.",
        throw: "Toss the cap 10–20 cm up and catch it. You can skip this one.",
        press: "Press the cap in this order (long press: hold for about a second):",
        flip: "Turn the cap over, wait a second, then turn it back.",
        drift: "Leave the cap lying still for 30 seconds. This measures how far the direction drifts on its own.",
      },
      start: "Start", done: "Done", redo: "Redo", skip: "Skip", next: "Next", close: "Close", report: "Bug report text",
      paused: "Link lost. The step restarts when the cap is back. If it doesn't come back, wait for Asleep and press the cap.",
      busy: "This cap is already being checked in another window.", other: "Check in progress",
      stepOf: "Step {n} of {total}", sleepStage: ["Disconnecting…", "Dozing off: don't touch, ~{left} s left", "Asleep: press the cap once", "Woke up"], lifts: "Pick-ups", recognised: "Recognised", tries: "Tries: {n}", count: "Steps", leans: "Leans", times: "Times", sec: "s", pick: "Which cap?", angle: "Turn", wrong: "wrong way",
      status: { pass: "Good", warn: "Notes", fail: "Failed", skip: "Skipped" },
      summary: "Results", flipStage: ["Lay it flat first", "Turn it over", "Now turn it back", "Done"],
      sug: { title: "Suggested changes", apply: "Save to options", err: "Not saved: {e}",
        note: "These go to the integration options; the link drops briefly and reconnects.",
        applied: "Saved. The cap reconnects with the new settings, or on its next press if it's asleep.",
        invert_rotation: "The knob runs backwards: toggle Invert knob direction.",
        sample_rate: "{loss}% of frames are lost: lower Sensor rate from {from} to {value} Hz.",
        multi_press_window: "Your double press arrived as two presses: set Multi-press window to {value} s (now {from} s).",
        shake: "Shake fired on its own ×{count}: turn it off.",
        tilt: "Tilt in the hand fired on its own ×{count}: turn it off." },
      values: { rest: "{rate} Hz of {asked}, {loss_pct}% lost, noise {noise_dps}°/s, via {via}", turn: "{steps} steps for {angle}°", drift: "{drift_deg_min}°/min", handle: "Pick-ups: {count}.", shake: "{count} of {tries}", sleep: "dozed for {doze_s} s" },
      reason: {
        loss: "{loss_pct}% of frames are lost. Move the cap closer to the receiver ({via}).",
        noise: "The sensor is noisy: the table is shaking or the cap was touched.",
        moved: "The cap moved. Redo it without touching the cap.",
        no_frames: "No data from the cap.",
        not_raised: "The dot edge wasn't lifted.",
        model_wrong: "The model tilted the wrong way. Run Calibrate again.",
        other_edge: "Wrong edge: lift the one with the dot.",
        model: "The model doesn't tilt like the cap.",
        short: "Only {angle}° turned: it takes two quarter turns.",
        long: "Turned {angle}°, more than two quarter turns. Redo it.",
        direction: "Turned the wrong way.",
        steps: "{steps} steps, expected {expected}.",
        wrong_way: "Steps came in the opposite direction.",
        knob_off: "The model turned with the cap. Knob steps weren't checked: the knob is off in the options.",
        lean_right: "Leaning right gave no event.",
        lean_left: "Leaning left gave no event.",
        lean_wrong: "A lean registered on the wrong side: hold the dot edge towards you.",
        missing: "Not received: {missing}.",
        not_flat: "Lay the cap flat.",
        not_flipped: "The cap wasn't turned over.",
        flip_events: "The side changed, but {flips} of 2 flip events arrived.",
        drift: "The direction drifts {drift_deg_min}°/min.",
        wrong_press: "That was {got}. Next: {want}.",
        not_detected: "The gesture wasn't recognised.",
        shake_missed: "{count} of {tries} shakes recognised.",
        handle_few: "Picked up {count} of 5 times.",
        woke_dozing: "It reconnected while dozing off instead of sleeping first. Redo it, and don't touch the cap until it says Asleep.",
        no_drop: "The link didn't drop. Redo it, and don't touch the cap until it says Asleep.",
        no_sleep: "It didn't fall asleep in time. Was it pressed while dozing? Each press restarts the 3 minutes.",
        no_wake: "The press didn't wake it.",
        long_doze: "It dozed for {doze_s} s: was it pressed meanwhile?",
        no_wake_press: "It woke up, but the press didn't register as a press.",
        extra: "Unexpected events: {extra}.",
      } },
    gestures: {
      press: "Press", single_press: "Press", double_press: "Double press", triple_press: "Triple press",
      long_press: "Long press", tap: "Tap", double_tap: "Double tap", shake: "Shake",
      throw: "Toss", flip: "Flip", rotate_cw: "Knob ↻", rotate_ccw: "Knob ↺", tilt_left: "Tilt ←", tilt_right: "Tilt →", wake: "Woke up", motion: "Motion",
    },
  },
  ru: {
    auto: "Авто", asleep: "Спит", dozing: "Засыпает",
    dozeHint: "Связь отключена после простоя. Ещё ~{n} с нажатия не дойдут, а каждое запускает 3 минуты заново: положите крышку и подождите",
    dozeLate: "Связь отключена после простоя. Пока крышка не уснёт, нажатия не дойдут, а каждое запускает 3 минуты заново: положите её и подождите", connected: "Подключена", streaming: "Данные идут", unresponsive: "Не отвечает",
    wake: "Нажмите на крышку, чтобы её разбудить", heading: "После перезапуска направление неизвестно: положите крышку точкой от себя и нажмите «Выровнять направление».", gyro: "Гироскоп, °/с",
    accel: "Акселерометр, g", roll: "Влево-вправо", pitch: "Вперёд-назад", yaw: "Поворот", calibrate: "Калибровка",
    editor: { title: "Заголовок", model: "Вид модели", show_model: "3D-модель и углы", chips: "Плашки состояния", show_values: "Полоски гироскопа и акселерометра",
      show_history: "График за последние 10 с", show_gestures: "Список жестов", buttons: "Кнопки", show_help: "Подсказки под кнопками",
      show_controls: "Кнопки и подсказки (старый переключатель)", admin: "«Калибровка» и «Проверка» видны только администраторам.",
      opt: { state: "Состояние", rate: "Частота", signal: "Сигнал, dBm", battery: "Батарея", link: "Дошло кадров, %", cap: "Triki (встроенная)", glb: "Flopsstuff с текстурами" } },
    help: { mark: "Жёлтая полоска на модели — это край с точкой над буквой Z (на фото обведена). По ней видно, как повёрнута модель.", cal: "<b>Калибровка</b> нужна каждой крышке один раз. Крышка лежит на столе точкой от вас, модель запоминает, как она лежит ровно, а потом вы подгоняете логотип. Сохраняется навсегда.", align: "<b>Выровнять направление</b> приходится время от времени. Наклон крышка чувствует сама, по силе тяжести, а куда она повёрнута — нет: компаса в ней нет. Поворот считает гироскоп, он понемногу сбивается, а после перезапуска Home Assistant поворот теряется. Если полоска на модели не там, где точка на крышке, положите крышку точкой от себя и нажмите эту кнопку. Калибровка останется.",
      led: "<b>Диод</b> включает и выключает зелёный огонёк крышки. Крышка не сообщает, горит ли он, поэтому кнопка подсвечена, только пока Вы его включили и крышка не задремала. Он сажает батарейку, так что без нужды его не включайте.",
      check: "<b>Проверка</b> шаг за шагом тестирует связь, крутилку, кнопку и включённые жесты и подсказывает, что поменять в настройках. Займёт несколько минут, любой шаг можно пропустить. Запустите её после установки или если жест срабатывает не так." },
    cal: { find: "Найдите на зелёной стороне точку над буквой Z (на фото обведена). На модели этот край отмечен жёлтой полоской.", flat: "Положите крышку на стол любой стороной вверх, этим краем от себя, отпустите и нажмите «Готово».", heading: "Положите крышку на стол этим краем от себя и нажмите «Готово»: полоска на модели тоже уйдёт на дальний край.", turned: "Направление выровнено", logo: "Теперь логотип. Металл обжимают под любым углом, поэтому его подгоняют один раз для каждой крышки. Положите крышку зелёной стороной вверх, буквой Z прямо, точкой сверху, и переверните через правый край. Поверните логотип ниже ползунком, чтобы он выглядел как на вашей крышке.", resin: "Зелёная сторона", metal: "После переворота", next: "Готово", cancel: "Отмена", skip: "Пропустить", saved: "Откалибровано",
      err: { moving: "Крышка двигается: замрите на секунду", not_flat: "Крышка лежит неровно", asleep: "Крышка спит: сначала разбудите её", no_data: "Данных пока нет: разбудите крышку" } },
    reset: "Выровнять направление",
    glist: { title: "Что умеет крышка", hint: "Нажмите на название, чтобы узнать, как это сделать. Жест загорается, когда крышка его замечает.", off: "выключено в настройках интеграции",
      knob: "Крутилка ↻ ↺", tilt: "Наклон ← →", how: { press: "Нажмите на крышку: она вся — кнопка.", double_press: "Два быстрых нажатия.", triple_press: "Три быстрых нажатия.",
        long_press: "Нажмите и подержите.", knob: "Крутите её прямо на столе, как ручку.", tilt: "Возьмите в руку и наклоните вправо или влево.",
        shake: "Резко встряхните несколько раз.", flip: "Переверните на другую сторону.", tap: "Стукните пальцем по столу рядом.", throw: "Подбросьте и поймайте." } },
    led: "Диод", button: "Кнопка", rate: "Гц", linkq: "Дошло кадров за сеанс", history: "Последние 10 с",
    check: { title: "Проверка", open: "Проверка",
      steps: { rest: "Лежит спокойно", flat: "Исходное положение", tilt: "Наклон", turn_cw: "Крутилка по часовой", turn_ccw: "Крутилка против часовой", handle: "Взять и положить", lean: "Наклон в руке", press: "Кнопка", flip: "Переворот", tap: "Стук", shake: "Встряхивание", throw: "Бросок", drift: "Уход направления", sleep: "Сон и пробуждение" },
      text: {
        identify: "Выберите крышку ниже или нажмите на неё.",
        wake: "Нажмите на крышку, чтобы её разбудить.",
        rest: "Положите крышку на стол и 10 секунд не трогайте: так измеряются связь и шум датчика.",
        flat: "Положите крышку на стол точкой от себя, отпустите и нажмите «Готово». От этого положения модель отсчитывает наклоны и повороты, и оно же сохранится как калибровка крышки.",
        tilt: "Приподнимите край с точкой примерно на 1 см (на кончик пальца) и подержите секунду. Модель должна наклониться как полупрозрачная подсказка.",
        turn_cw: "Поверните крышку на столе на четверть оборота по часовой: полоска уйдёт с дальнего края вправо. Отпустите, перехватите и поверните ещё на четверть. Потом нажмите «Готово».",
        turn_ccw: "Теперь против часовой: две четверти оборота, между ними отпустите крышку. Потом нажмите «Готово».",
        knobOff: "Крутилка выключена в настройках, поэтому шаг проверит только, что модель поворачивается вместе с крышкой.",
        tap: "Стукните пальцем по столу рядом с крышкой 2–3 раза, с паузой в секунду.",
        shake: "Возьмите крышку в руку и встряхните 3 раза с паузой в пару секунд — так, как будете делать потом.",
        handle: "Возьмите крышку со стола, как перед жестом, подержите и положите обратно. 5 раз, каждый раз чуть по-разному. Специально не крутите и не наклоняйте: всё, что сработает, — ложная тревога. Подъём засчитывается, когда крышка снова спокойно лежит на столе.",
        sleep: "Положите крышку и не трогайте. Сейчас Home Assistant отключит её, как после простоя: около 3 минут она засыпает, и нажатия в это время не доходят. Когда здесь появится «Спит», нажмите на крышку один раз. Шаг можно пропустить.",
        lean: "Держите крышку в руке ровно, краем с точкой к себе. Наклоните вправо примерно на 30°, пока не появится «Наклон →», и выровняйте; потом так же влево. Так 3 раза.",
        throw: "Подбросьте крышку на 10–20 см и поймайте. Шаг можно пропустить.",
        press: "Нажимайте в таком порядке (долгое нажатие — держите около секунды):",
        flip: "Переверните крышку, подождите секунду и верните обратно.",
        drift: "Оставьте крышку лежать 30 секунд: так видно, насколько уплывает направление без движения.",
      },
      start: "Начать", done: "Готово", redo: "Повторить", skip: "Пропустить", next: "Дальше", close: "Закрыть", report: "Текст для отчёта об ошибке",
      paused: "Связь пропала. Шаг начнётся заново, когда крышка вернётся. Если не возвращается, дождитесь «Спит» и нажмите на крышку.",
      busy: "Эту крышку уже проверяют в другом окне.", other: "Идёт проверка",
      stepOf: "Шаг {n} из {total}", sleepStage: ["Отключаю…", "Засыпает: не трогайте, ещё ~{left} с", "Спит: нажмите на крышку один раз", "Проснулась"], lifts: "Подъёмы", recognised: "Распознано", tries: "Попыток: {n}", count: "Шаги", leans: "Наклоны", times: "Раз", sec: "с", pick: "Какую крышку проверяем?", angle: "Поворот", wrong: "не в ту сторону",
      status: { pass: "В порядке", warn: "Есть замечания", fail: "Не прошло", skip: "Пропущено" },
      summary: "Итог", flipStage: ["Сначала положите плашмя", "Переверните", "Теперь верните обратно", "Готово"],
      sug: { title: "Что стоит поменять", apply: "Сохранить", err: "Не сохранилось: {e}",
        note: "Сохранится в настройках интеграции; связь прервётся и восстановится.",
        applied: "Сохранено. Крышка подключится с новыми настройками, а если спит — после следующего нажатия.",
        invert_rotation: "Повороты пришли наоборот: переключить «Обратное направление крутилки».",
        sample_rate: "Теряется {loss}% кадров: «Частота датчиков» — {value} Гц вместо {from}.",
        multi_press_window: "Двойное нажатие пришло как два одиночных: «Окно двойного и тройного нажатия» — {value} с вместо {from} с.",
        shake: "«Встряхивание» сработало само ×{count}: выключить его.",
        tilt: "«Наклон в руке» сработал сам ×{count}: выключить его." },
      values: { rest: "{rate} Гц из {asked}, потеряно {loss_pct}%, шум {noise_dps}°/с, через {via}", turn: "Шаги: {steps} за {angle}°", drift: "{drift_deg_min}°/мин", handle: "Подъёмов: {count}.", shake: "{count} из {tries}", sleep: "засыпала {doze_s} с" },
      reason: {
        loss: "Теряется {loss_pct}% кадров. Поставьте крышку ближе к приёмнику ({via}).",
        noise: "Датчик шумит: стол дрожит или крышку задели.",
        moved: "Крышка сдвинулась. Повторите и не трогайте её.",
        no_frames: "От крышки нет данных.",
        not_raised: "Край с точкой не приподняли.",
        model_wrong: "Модель наклонилась не туда. Повторите калибровку.",
        other_edge: "Это не тот край. Приподнимите край с точкой.",
        model: "Модель наклоняется не так, как крышка.",
        short: "Поворот всего на {angle}°, а нужно две четверти оборота.",
        long: "Поворот на {angle}° — больше двух четвертей. Повторите.",
        direction: "Повернули не в ту сторону.",
        steps: "Шагов {steps}, а ожидалось {expected}.",
        wrong_way: "Шаги шли в обратную сторону.",
        knob_off: "Модель повернулась вместе с крышкой. Шаги крутилки не проверялись: она выключена в настройках.",
        lean_right: "На наклон вправо событие не пришло.",
        lean_left: "На наклон влево событие не пришло.",
        lean_wrong: "Пришёл наклон в другую сторону: держите крышку краем с точкой к себе.",
        missing: "Не пришло: {missing}.",
        not_flat: "Положите крышку плашмя.",
        not_flipped: "Крышку не перевернули.",
        flip_events: "Сторона сменилась, но событий переворота пришло {flips} из 2.",
        drift: "Направление уплывает на {drift_deg_min}°/мин.",
        wrong_press: "Это было «{got}», а сейчас нужно «{want}».",
        not_detected: "Жест не распознан.",
        shake_missed: "Распознано встряхиваний: {count} из {tries}.",
        handle_few: "Подъёмов {count} из 5.",
        woke_dozing: "Крышка подключилась, не успев уснуть. Повторите и не трогайте её, пока не появится «Спит».",
        no_drop: "Связь не прервалась. Повторите и не трогайте крышку, пока не появится «Спит».",
        no_sleep: "Крышка не уснула вовремя. Может, на неё нажали, пока она засыпала? Каждое нажатие запускает 3 минуты заново.",
        no_wake: "Нажатие не разбудило крышку.",
        long_doze: "Засыпала {doze_s} с: на неё нажимали в это время?",
        no_wake_press: "Крышка проснулась, но события нажатия не было.",
        extra: "Сработало лишнее: {extra}.",
      } },
    nodevice: "Крышка Triki не найдена",
    gestures: {
      press: "Нажатие", single_press: "Нажатие", double_press: "Двойное нажатие", triple_press: "Тройное нажатие",
      long_press: "Долгое нажатие", tap: "Стук", double_tap: "Двойной стук", shake: "Встряхивание",
      throw: "Бросок", flip: "Переворот", rotate_cw: "Крутилка ↻", rotate_ccw: "Крутилка ↺", tilt_left: "Наклон ←", tilt_right: "Наклон →", wake: "Проснулась",
      motion: "Движение",
    },
  },
  pl: {
    auto: "Auto", asleep: "Śpi", dozing: "Zasypia",
    dozeHint: "Rozłączony po bezczynności. Przez ~{n} s naciśnięcia nie dotrą, a każde odlicza 3 minuty od nowa: odłóż kapsel i poczekaj",
    dozeLate: "Rozłączony po bezczynności. Dopóki nie zaśnie, naciśnięcia nie dotrą, a każde odlicza 3 minuty od nowa: odłóż kapsel i poczekaj", connected: "Połączony", streaming: "Na żywo", unresponsive: "Nie odpowiada",
    wake: "Naciśnij kapsel, żeby go obudzić", heading: "Po restarcie kierunek jest nieznany: połóż kapsel kropką od siebie i naciśnij „Wyrównaj kierunek”.", gyro: "Żyroskop, °/s",
    accel: "Akcelerometr, g", roll: "Lewo-prawo", pitch: "Przód-tył", yaw: "Obrót wokół osi",
    editor: { title: "Tytuł", model: "Wygląd modelu", show_model: "Model 3D i kąty", chips: "Plakietki stanu", show_values: "Paski żyroskopu i akcelerometru",
      show_history: "Wykres ostatnich 10 s", show_gestures: "Lista gestów", buttons: "Przyciski", show_help: "Pomoc pod przyciskami",
      show_controls: "Przyciski i pomoc (stary przełącznik)", admin: "Przyciski Kalibruj i Test widzą tylko administratorzy.",
      opt: { state: "Stan", rate: "Częstotliwość", signal: "Sygnał, dBm", battery: "Bateria", link: "Odebrane ramki, %", cap: "Triki (wbudowany)", glb: "Flopsstuff z teksturą" } },
    help: { mark: "Żółty pasek na modelu to krawędź z kropką nad literą Z (zakreśloną na zdjęciu). Po nim poznasz, jak model jest obrócony.", cal: "<b>Kalibruj</b> raz na każdy kapsel. Kapsel leży na stole kropką od ciebie: model uczy się, jak u tego kapsla wygląda poziom, a potem dopasowujesz logo. Wynik zostaje na stałe.", align: "<b>Wyrównaj kierunek</b> przyda się co jakiś czas. Przechył kapsel wyczuwa sam, z grawitacji, ale nie wie, w którą stronę jest obrócony, bo nie ma kompasu. Obrót liczy żyroskop, który z czasem dryfuje, a restart Home Assistanta go kasuje. Gdy pasek na modelu jest przy innej krawędzi niż kropka na kapslu, połóż kapsel kropką od siebie i naciśnij ten przycisk. Kalibracja zostaje bez zmian.",
      led: "<b>Dioda</b> włącza i wyłącza zielone światełko w kapslu. Kapsel nie zgłasza, czy świeci, więc przycisk jest podświetlony tylko po włączeniu, dopóki kapsel nie zaśnie. Zjada baterię, więc nie włączaj jej bez potrzeby.",
      check: "<b>Test</b> sprawdza krok po kroku połączenie, pokrętło, przycisk i włączone gesty, a potem podpowiada, co zmienić w opcjach. Zajmuje kilka minut, każdy krok można pominąć. Zrób go po instalacji albo wtedy, gdy któryś gest szwankuje." },
    calibrate: "Kalibruj",
    cal: { find: "Znajdź na zielonej stronie kropkę nad literą Z (zakreśloną na zdjęciu). Na modelu tę krawędź oznacza żółty pasek.", flat: "Połóż kapsel na stole dowolną stroną do góry, tą krawędzią od siebie. Puść go i naciśnij Gotowe.", heading: "Połóż kapsel na stole tą krawędzią od siebie i naciśnij Gotowe: pasek na modelu też przejdzie na krawędź najdalej od ciebie.", turned: "Kierunek wyrównany", logo: "Teraz logo (raz na kapsel: metalową część zaciśnięto pod przypadkowym kątem). Połóż kapsel zieloną stroną do góry, z literą Z prosto i kropką na górze, a potem odwróć go przez prawą krawędź. Obracaj logo poniżej suwakiem, aż będzie wyglądać jak na twoim kapslu.", resin: "Zielona strona", metal: "Po odwróceniu", next: "Gotowe", cancel: "Anuluj", skip: "Pomiń", saved: "Skalibrowano",
      err: { moving: "Kapsel się rusza: niech poleży chwilę bez ruchu", not_flat: "Kapsel nie leży płasko", asleep: "Kapsel śpi: najpierw go obudź", no_data: "Jeszcze brak danych: obudź kapsel" } },
    glist: { title: "Co potrafi kapsel", hint: "Kliknij nazwę, żeby zobaczyć jak. Gest się podświetla, gdy kapsel go wykona.", off: "wyłączone w opcjach integracji",
      knob: "Pokrętło ↻ ↺", tilt: "Przechył ← →", how: { press: "Naciśnij cały kapsel.", double_press: "Dwa szybkie naciśnięcia.", triple_press: "Trzy szybkie naciśnięcia.",
        long_press: "Naciśnij i przytrzymaj.", knob: "Obracaj go płasko na stole jak pokrętło.", tilt: "Trzymaj go w dłoni i przechylaj w prawo lub w lewo.",
        shake: "Potrząśnij nim energicznie kilka razy.", flip: "Odwróć go na drugą stronę.", tap: "Stuknij palcem w stół obok niego.", throw: "Podrzuć go i złap." } },
    reset: "Wyrównaj kierunek", led: "Dioda", button: "Przycisk", rate: "Hz", linkq: "Odebrane ramki w sesji", history: "Ostatnie 10 s",
    check: { title: "Test", open: "Test",
      steps: { rest: "Spoczynek", flat: "Pozycja wyjściowa", tilt: "Przechył", turn_cw: "Pokrętło w prawo", turn_ccw: "Pokrętło w lewo", handle: "Podnieś i odłóż", lean: "Przechył w dłoni", press: "Przycisk", flip: "Odwrócenie", tap: "Stuknięcie", shake: "Potrząśnięcie", throw: "Podrzut", drift: "Dryf kierunku", sleep: "Sen i pobudka" },
      text: {
        identify: "Wybierz kapsel poniżej albo go naciśnij.",
        wake: "Naciśnij kapsel, żeby go obudzić.",
        rest: "Połóż kapsel na stole i nie dotykaj go przez 10 sekund. Ten krok mierzy łącze i szum czujnika.",
        flat: "Połóż kapsel na stole kropką od siebie, puść i naciśnij Gotowe. Od tej pozycji model liczy przechyły i obroty; zapisze się ona też jako kalibracja kapsla.",
        tilt: "Unieś krawędź z kropką o ok. 1 cm (na grubość opuszka) i przytrzymaj sekundę. Model powinien przechylić się tak jak półprzezroczysta podpowiedź.",
        turn_cw: "Obróć kapsel na stole o ćwierć obrotu w prawo: pasek przejdzie z dalszej krawędzi na prawą. Puść, chwyć na nowo i obróć o kolejną ćwiartkę. Potem naciśnij Gotowe.",
        turn_ccw: "To samo w lewo: dwie ćwiartki, a między nimi puść kapsel. Potem naciśnij Gotowe.",
        knobOff: "Pokrętło jest wyłączone w opcjach, więc ten krok sprawdza tylko, czy model obraca się razem z kapslem.",
        tap: "Stuknij palcem w stół obok kapsla 2–3 razy, co sekundę.",
        shake: "Weź kapsel do ręki i potrząśnij nim 3 razy, co kilka sekund, tak jak będziesz to robić na co dzień.",
        handle: "Podnieś kapsel ze stołu tak, jak robisz to przed gestem, potrzymaj i odłóż. 5 razy, za każdym razem trochę inaczej. Celowo go nie obracaj ani nie przechylaj: wszystko, co wtedy zadziała, to fałszywy alarm. Podniesienie się liczy, gdy kapsel znów leży nieruchomo na stole.",
        sleep: "Odłóż kapsel i nie dotykaj go. Home Assistant rozłączy go teraz jak po bezczynności: przez około 3 minuty kapsel zasypia i naciśnięcia nie docierają. Gdy pojawi się tu „Śpi”, naciśnij kapsel raz. Ten krok możesz pominąć.",
        lean: "Trzymaj kapsel poziomo w dłoni, krawędzią z kropką do siebie. Przechyl go w prawo o ok. 30°, aż pojawi się „Przechył →”, i wróć do poziomu; potem w lewo i znów do poziomu. Trzy razy.",
        throw: "Podrzuć kapsel na 10–20 cm i złap. Ten krok możesz pominąć.",
        press: "Naciskaj w tej kolejności (długie naciśnięcie: przytrzymaj ok. sekundy):",
        flip: "Odwróć kapsel na drugą stronę, odczekaj sekundę i odwróć z powrotem.",
        drift: "Zostaw kapsel w spokoju na 30 sekund. Ten krok mierzy, jak mocno kierunek dryfuje bez ruchu.",
      },
      start: "Start", done: "Gotowe", redo: "Powtórz", skip: "Pomiń", next: "Dalej", close: "Zamknij", report: "Tekst do zgłoszenia błędu",
      paused: "Łącze zerwane. Krok zacznie się od nowa, gdy kapsel wróci. Jeśli nie wraca, poczekaj na „Śpi” i naciśnij kapsel.",
      busy: "Ten kapsel jest już testowany w innym oknie.", other: "Trwa test",
      stepOf: "Krok {n} z {total}", sleepStage: ["Rozłączam…", "Zasypia: nie dotykaj, jeszcze ~{left} s", "Śpi: naciśnij kapsel raz", "Obudzony"], lifts: "Podniesienia", recognised: "Rozpoznane", tries: "Prób: {n}", count: "Kroki", leans: "Przechyły", times: "Razy", sec: "s", pick: "Który kapsel?", angle: "Obrót", wrong: "w złą stronę",
      status: { pass: "Dobrze", warn: "Uwagi", fail: "Nie wyszło", skip: "Pominięto" },
      summary: "Wynik", flipStage: ["Najpierw połóż płasko", "Odwróć", "Teraz z powrotem", "Gotowe"],
      sug: { title: "Proponowane zmiany", apply: "Zapisz w opcjach", err: "Nie zapisano: {e}",
        note: "Zapisze się w opcjach integracji; połączenie na chwilę się zerwie i wróci.",
        applied: "Zapisano. Kapsel połączy się z nowymi ustawieniami, a jeśli śpi, to przy najbliższym naciśnięciu.",
        invert_rotation: "Obroty wyszły w odwrotną stronę: przełącz „Odwróć kierunek pokrętła”.",
        sample_rate: "Ginie {loss}% ramek: obniż częstotliwość czujników z {from} do {value} Hz.",
        multi_press_window: "Twoje podwójne naciśnięcie doszło jako dwa pojedyncze: ustaw „Czas na podwójne/potrójne naciśnięcie” na {value} s (teraz {from} s).",
        shake: "Potrząśnięcie zadziałało samo ×{count}: wyłącz je.",
        tilt: "Przechył w dłoni zadziałał sam ×{count}: wyłącz go." },
      values: { rest: "{rate} Hz z {asked}, utrata {loss_pct}%, szum {noise_dps}°/s, przez {via}", turn: "{steps} kroków na {angle}°", drift: "{drift_deg_min}°/min", handle: "Podniesień: {count}.", shake: "{count} z {tries}", sleep: "zasypiał {doze_s} s" },
      reason: {
        loss: "Ginie {loss_pct}% ramek. Przysuń kapsel bliżej odbiornika ({via}).",
        noise: "Czujnik szumi: stół drga albo ktoś dotknął kapsla.",
        moved: "Kapsel się poruszył. Powtórz, nie dotykając go.",
        no_frames: "Brak danych z kapsla.",
        not_raised: "Krawędź z kropką się nie uniosła.",
        model_wrong: "Model przechylił się w złą stronę. Skalibruj kapsel jeszcze raz.",
        other_edge: "To nie ta krawędź. Unieś tę z kropką.",
        model: "Model przechyla się inaczej niż kapsel.",
        short: "Obrót tylko o {angle}°: potrzeba dwóch ćwiartek.",
        long: "Obrót o {angle}°, czyli więcej niż dwie ćwiartki. Powtórz.",
        direction: "Obrót w drugą stronę.",
        steps: "{steps} kroków, a powinno być {expected}.",
        wrong_way: "Kroki szły w przeciwną stronę.",
        knob_off: "Model obrócił się razem z kapslem. Kroków pokrętła nie sprawdzano, bo pokrętło jest wyłączone w opcjach.",
        lean_right: "Przechył w prawo nic nie wywołał.",
        lean_left: "Przechył w lewo nic nie wywołał.",
        lean_wrong: "Wykryto przechył w drugą stronę: trzymaj kapsel krawędzią z kropką do siebie.",
        missing: "Nie dotarło: {missing}.",
        not_flat: "Połóż kapsel płasko.",
        not_flipped: "Kapsel nie został odwrócony.",
        flip_events: "Strona się zmieniła, ale doszło {flips} z 2 zdarzeń odwrócenia.",
        drift: "Kierunek ucieka o {drift_deg_min}°/min.",
        wrong_press: "To było „{got}”, a teraz trzeba „{want}”.",
        not_detected: "Nie rozpoznano gestu.",
        shake_missed: "Rozpoznano {count} z {tries} potrząśnięć.",
        handle_few: "Podniesień: {count} z 5.",
        woke_dozing: "Połączył się w trakcie zasypiania, a powinien najpierw zasnąć. Powtórz i nie dotykaj kapsla, aż pojawi się „Śpi”.",
        no_drop: "Łącze się nie zerwało. Powtórz i nie dotykaj kapsla, aż pojawi się „Śpi”.",
        no_sleep: "Nie zasnął na czas. Czy był naciskany w trakcie zasypiania? Każde naciśnięcie odlicza 3 minuty od nowa.",
        no_wake: "Naciśnięcie go nie obudziło.",
        long_doze: "Zasypiał {doze_s} s: czy ktoś go w tym czasie naciskał?",
        no_wake_press: "Obudził się, ale budzące naciśnięcie nie doszło jako „Naciśnięcie”.",
        extra: "Zadziałało coś nieproszonego: {extra}.",
      } },
    nodevice: "Nie znaleziono kapsla Triki",
    gestures: {
      press: "Naciśnięcie", single_press: "Naciśnięcie", double_press: "Podwójne naciśnięcie",
      triple_press: "Potrójne naciśnięcie", long_press: "Długie naciśnięcie", tap: "Stuknięcie",
      double_tap: "Podwójne stuknięcie", shake: "Potrząśnięcie", throw: "Podrzut", flip: "Odwrócenie",
      rotate_cw: "Pokrętło ↻", rotate_ccw: "Pokrętło ↺", tilt_left: "Przechył ←", tilt_right: "Przechył →", wake: "Pobudka", motion: "Ruch",
    },
  },
};

const AXIS_COLORS = ["#ef5350", "#66bb6a", "#42a5f5"];
const HISTORY_S = 10;
const GYRO_RANGE = 500; // °/s at full bar
const ACCEL_RANGE = 2; // g at full bar

const PICK_KEY = "triki-card-pick";
let threePromise = null;
let modelPromise = null;
let capPromise = null;
let checkPromise = null;
function loadCheck() {
  if (!checkPromise) checkPromise = import(asset("triki-check.js"));
  return checkPromise;
}
const CHECK_RENEW_MS = 10000; // the server lets a check lapse 30 s after the last renewal
const GHOST_TILT = (20 * Math.PI) / 180;
const DEG = Math.PI / 180;
const smooth = (x) => (x <= 0 ? 0 : x >= 1 ? 1 : x * x * (3 - 2 * x));
const between = (t, a, b) => smooth((t - a) / (b - a));
// The hint's moves for the steps without a pose of their own: lift (scene units,
// the cap is ~2.3 across), tilt and lean (radians), over one loop of `sec`.
export function ghostMotion(type, sec) {
  if (type === "lift") { // up off the table, held a moment, back down
    const t = sec % 4;
    const up = between(t, 0, 0.9) - between(t, 2.1, 3.1);
    return { lift: 0.45 * up, tilt: 25 * DEG * up * (1 - 0.3 * Math.sin(t * 6) * (t > 0.9 && t < 2.1)) };
  }
  if (type === "lean") { // in the hand: lean right, back, lean left, back
    const t = sec % 4;
    const lean = 40 * DEG * (between(t, 0, 0.7) - between(t, 1.2, 1.9) - between(t, 2, 2.7) + between(t, 3.2, 3.9));
    return { lift: 0.25, lean };
  }
  if (type === "press") { // pushed down once, then a pause
    const t = sec % 2;
    return { lift: -0.15 * (between(t, 0, 0.1) - between(t, 0.3, 0.4)) };
  }
  if (type === "shake") { // a quick burst back and forth, then a pause
    const t = sec % 2.5;
    return { lift: 0.25, tilt: t < 1.2 ? 35 * DEG * Math.sin(t * 2 * Math.PI * 4) * Math.sin(Math.PI * t / 1.2) : 0 };
  }
  if (type === "tap") { // a jolt: two quick knocks
    const t = sec % 2;
    const knock = (a) => 0.12 * Math.sin(Math.PI * Math.min(1, Math.max(0, (t - a) / 0.12)));
    return { lift: knock(0) + knock(0.35) };
  }
  if (type === "throw") { // tossed up and caught
    const t = sec % 3;
    const f = t < 1 ? 4 * t * (1 - t) : 0;
    return { lift: 0.25 + 0.4 * f, tilt: 2 * Math.PI * smooth(t) * (t < 1) };
  }
  return null;
}
function loadCap() {
  if (!capPromise) capPromise = import(asset("triki-cap.js"));
  return capPromise;
}
function loadThree() {
  if (!threePromise) threePromise = import(asset("triki-three.js"));
  return threePromise;
}
function loadModel(T) {
  if (!modelPromise) modelPromise = new T.GLTFLoader().loadAsync(asset("triki.glb"));
  return modelPromise;
}

const CSS = `
  /* one compact block, centred on wide dashboards (panel view) */
  :host { display: block; max-width: 1040px; margin: 0 auto; }
  ha-card { display: block; overflow: hidden; }
  button { transition: transform .12s, background .2s, border-color .2s, color .2s, box-shadow .2s; }
  button:not(:disabled):hover { box-shadow: 0 2px 10px rgba(0,0,0,.25); }
  button:not(:disabled):active { transform: scale(.96); }
  .head { display: flex; align-items: center; gap: 8px; padding: 12px 16px 4px; flex-wrap: wrap; }
  .name { font-size: 1.3em; font-weight: 500; margin-right: auto; }
  .chip { display: inline-flex; align-items: center; gap: 4px; font-size: 0.85em; padding: 2px 8px;
    border-radius: 12px; background: var(--secondary-background-color); color: var(--secondary-text-color); }
  .chip[hidden] { display: none; }
  .tabs { display: flex; gap: 8px; padding: 8px 16px 0; overflow-x: auto; scrollbar-width: none; }
  .tabs[hidden] { display: none; }
  .tab { display: inline-flex; align-items: center; gap: 6px; flex: none; font: inherit; font-size: .95em;
    padding: 8px 16px; border-radius: 18px; cursor: pointer; border: 1px solid var(--divider-color);
    background: none; color: var(--secondary-text-color); white-space: nowrap; }
  .tab.sel { border-color: var(--primary-color); color: var(--primary-text-color);
    background: rgba(var(--rgb-primary-color, 3,169,244), .12); }
  .tab .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--disabled-text-color, #777); }
  .tab .dot.live { background: #66bb6a; box-shadow: 0 0 6px #66bb6a; }
  .chip.live { background: rgba(102,187,106,.2); color: #66bb6a; }
  .chip.warn { background: rgba(255,152,0,.2); color: #ff9800; }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
  .chip.live .dot { animation: pulse 1.2s infinite; }
  .checkpanel .dot { display: inline-block; margin-right: 8px; vertical-align: middle; background: var(--disabled-text-color, #777); }
  .checkpanel details.report { margin-top: 10px; color: var(--secondary-text-color); }
  .checkpanel details.report textarea { width: 100%; box-sizing: border-box; margin-top: 6px; font: 12px monospace; background: transparent; color: inherit; border: 1px solid var(--divider-color, #444); border-radius: 6px; }
  .checkpanel .dot.on { background: #66bb6a; }
  @keyframes pulse { 50% { opacity: .3; } }
  /* max-width, or the 260 px min-height widens it through the aspect ratio to
     416 px and a phone-width card cuts off its right side (the Button light) */
  .stage { position: relative; aspect-ratio: 16 / 10; min-height: 260px; max-width: 100%; }
  canvas.gl { position: absolute; inset: 0; width: 100%; height: 100%; display: block;
    transition: opacity .5s, filter .5s; }
  .stage.bump { animation: bump .35s ease-out; }
  @keyframes bump { 30% { box-shadow: inset 0 0 0 3px rgba(var(--rgb-primary-color, 3,169,244), .55); } }
  /* clear of the Button indicator; on a narrow card the labels wrap */
  .angles { position: absolute; left: 12px; right: 96px; top: 8px; display: flex; gap: 14px; pointer-events: none; }
  .angle { display: flex; flex-direction: column; min-width: 0; }
  .angle small { font-size: .72em; color: var(--secondary-text-color); text-transform: uppercase; letter-spacing: .04em; }
  .angle b { font-size: 1.35em; font-variant-numeric: tabular-nums; min-width: 3.2em; }
  .btn-ind { position: absolute; right: 12px; top: 10px; display: flex; align-items: center; gap: 6px;
    font-size: .8em; color: var(--secondary-text-color); }
  .btn-ind .led { width: 14px; height: 14px; border-radius: 50%; border: 2px solid var(--divider-color);
    transition: background .08s, box-shadow .08s; }
  .btn-ind.on .led { background: #66bb6a; box-shadow: 0 0 10px #66bb6a; border-color: #66bb6a; }
  .toast { position: absolute; left: 50%; bottom: 14px; transform: translateX(-50%) scale(.9); opacity: 0;
    background: var(--primary-color); color: var(--text-primary-color, #fff); padding: 6px 14px;
    border-radius: 16px; font-weight: 500; transition: opacity .2s, transform .2s; pointer-events: none; }
  .toast.show { opacity: 1; transform: translateX(-50%) scale(1); }
  .sleep { position: absolute; inset: 0; display: none; align-items: flex-end; justify-content: center; text-align: center; padding-left: 24px; padding-right: 24px;
    padding-bottom: 16px; color: var(--secondary-text-color); font-size: .9em; pointer-events: none; }
  .asleep .sleep { display: flex; }
  .headhint { position: absolute; left: 0; right: 0; bottom: 0; padding: 0 24px 14px; text-align: center;
    color: var(--warning-color, #ffa600); font-size: .9em; pointer-events: none; }
  .checking .headhint { display: none; }
  .asleep canvas.gl { opacity: .45; filter: grayscale(.7); }
  .values { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 20px; padding: 8px 16px 4px; }
  .values h4 { margin: 4px 0 2px; font-size: .78em; font-weight: 500; color: var(--secondary-text-color); }
  .row { display: grid; grid-template-columns: 14px 1fr 4.2em; align-items: center; gap: 6px; height: 20px; }
  .row span { font-size: .8em; font-weight: 600; }
  .row output { text-align: right; font-variant-numeric: tabular-nums; font-size: .9em; }
  .bar { position: relative; height: 6px; border-radius: 3px; background: var(--divider-color); overflow: hidden; }
  .bar i { position: absolute; top: 0; bottom: 0; left: 50%; width: 0; border-radius: 3px;
    transition: width .08s linear, left .08s linear; }
  .bar::after { content: ""; position: absolute; left: 50%; top: -2px; bottom: -2px; width: 1px; background: var(--secondary-text-color); opacity: .5; }
  .chart { padding: 4px 16px 0; }
  .glist { padding: 8px 16px 0; }
  .glist small { font-size: .72em; color: var(--secondary-text-color); }
  .gitems { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px; }
  .gitem { font: inherit; font-size: .8em; padding: 3px 10px; border-radius: 12px; cursor: pointer;
    border: 1px solid var(--divider-color); background: none; color: var(--primary-text-color);
    transition: background .4s, border-color .4s, color .4s; }
  .gitem.sel { border-color: var(--primary-color); }
  .gitem.off { color: var(--secondary-text-color); opacity: .55; text-decoration: line-through; }
  .gitem.hit { background: var(--primary-color); border-color: var(--primary-color); color: #fff; transition: none; }
  .ghow { margin: 4px 0 0; font-size: .78em; color: var(--secondary-text-color); min-height: 1.3em; }
  .chart small { font-size: .72em; color: var(--secondary-text-color); }
  canvas.hist { width: 100%; height: 70px; display: block; }
  /* two rows on a narrow card: four Russian labels need ~530 px in one */
  .actions { display: flex; flex-wrap: wrap; gap: 10px; padding: 10px 16px 16px; }
  .actions button { flex: 1 1 0; min-width: 0; display: inline-flex; align-items: center; justify-content: center; gap: 8px;
    font: inherit; font-size: 1em; font-weight: 500; min-height: 52px; padding: 10px 14px; border-radius: 12px; cursor: pointer;
    border: 1px solid var(--divider-color); background: var(--secondary-background-color); color: var(--primary-text-color); }
  .actions button:disabled { opacity: .45; cursor: default; }
  .actions button.on { border-color: #66bb6a; color: #66bb6a; }
  .actions .lbl { display: flex; flex-direction: column; align-items: center; line-height: 1.2; text-align: center; }
  .actions .lbl small { font-size: .74em; font-weight: 400; color: var(--secondary-text-color); }
  .help { padding: 0 16px 14px; font-size: .88em; color: var(--secondary-text-color); }
  .help p { margin: 8px 0 0; line-height: 1.4; }
  .help b { color: var(--primary-text-color); font-weight: 500; }
  .help .front { display: flex; gap: 12px; align-items: center; margin-top: 2px; }
  .help .front p { margin: 0 0 4px; }
  .pic { position: relative; flex: none; width: 64px; height: 64px; }
  .pic img { width: 100%; height: 100%; border-radius: 50%; }
  .pic i { position: absolute; left: 50%; top: 9%; width: 14px; height: 14px; margin: -7px 0 0 -7px;
    border: 2px solid #ffd54f; border-radius: 50%; box-shadow: 0 0 6px #ffd54f; }
  .wizard { position: absolute; inset: 0; display: none; flex-direction: column; align-items: center;
    justify-content: center; gap: 10px; padding: 16px; text-align: center;
    background: color-mix(in srgb, var(--card-background-color, #1c1f23) 88%, transparent); }
  .wizard.show { display: flex; animation: fade .25s ease-out; }
  @keyframes fade { from { opacity: 0; transform: scale(.98); } }
  .wizard p { margin: 0; max-width: 32em; }
  .wizard .err { color: var(--error-color, #ef5350); min-height: 1.2em; font-size: .9em; }
  .wizard .row { display: flex; gap: 8px; }
  .logo-match { display: flex; align-items: center; gap: 18px; }
  .logo-match[hidden], .slider[hidden], .find[hidden] { display: none; }
  .find { display: flex; align-items: center; gap: 12px; text-align: left; max-width: 32em; }
  .find p { margin: 0; }
  .find .pic { width: 84px; height: 84px; }
  .pic i { z-index: 1; }
  .logo-match figure { margin: 0; display: flex; flex-direction: column; align-items: center; gap: 4px; }
  .logo-match img { width: 92px; height: 92px; border-radius: 50%; transition: transform .15s; }
  .logo-match figcaption { font-size: .78em; color: var(--secondary-text-color); }
  .logo-match .arrow { font-size: 22px; color: var(--secondary-text-color); }
  .slider { display: flex; align-items: center; gap: 8px; width: min(360px, 90%); }
  .slider input { flex: 1; accent-color: var(--primary-color); }
  .slider button { width: 40px; height: 40px; padding: 0; font-size: 18px; }
  .slider output { min-width: 3.2em; text-align: right; font-variant-numeric: tabular-nums; }
  .wizard button { font: inherit; font-size: 1.05em; min-height: 48px; padding: 10px 24px; border-radius: 12px; cursor: pointer;
    border: 1px solid var(--divider-color); background: var(--secondary-background-color); color: var(--primary-text-color); }
  .wizard button.primary { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
  .body { display: block; }
  /* wide card (set from a ResizeObserver): 3D on the left, readings and controls on the right */
  .wide .body { display: grid; grid-template-columns: minmax(0, 1fr) 340px; align-items: stretch; }
  .wide .stage { aspect-ratio: auto; height: 400px; min-height: 0; }
  .wide .side { display: flex; flex-direction: column; border-left: 1px solid var(--divider-color); }
  .wide .side .values { grid-template-columns: 1fr; padding-top: 12px; }
  .wide .side .row { height: 22px; }
  .wide .side .chart { flex: 1; }
  .wide .side canvas.hist { height: 80px; }
  .wide .side .actions { flex-direction: column; flex-wrap: nowrap; margin-top: auto; }
  .wide .side .actions button { flex: none; }
  /* guided check */
  .chip.check { background: rgba(255,193,7,.2); color: #ffc107; }
  .checkbar { position: absolute; left: 12px; right: 12px; bottom: 10px; display: none; flex-direction: column; gap: 4px; pointer-events: none; }
  .checking .checkbar { display: flex; }
  .checkbar b { font-size: 1.05em; text-shadow: 0 1px 4px rgba(0,0,0,.6); }
  .checkbar .time { height: 6px; border-radius: 3px; background: var(--divider-color); overflow: hidden; }
  .checkbar .time i { display: block; height: 100%; width: 0; background: var(--primary-color); transition: width .25s linear; }
  .checking .angles { opacity: .55; }
  .checking .sleep { display: none; }
  .checkpanel { display: none; flex-direction: column; gap: 10px; padding: 14px 16px 16px; }
  .checking .checkpanel { display: flex; }
  .checking .side > :not(.checkpanel) { display: none; }
  /* show_model: false keeps the stage for a check or a calibration, which run on it */
  .nomodel:not(.checking):not(.calibrating) .stage { display: none; }
  .wide.nomodel:not(.checking):not(.calibrating) .body { display: block; }
  .wide.nomodel:not(.checking):not(.calibrating) .side { border-left: none; }
  .head .chip[data-off] { display: none !important; }
  .actions [data-off] { display: none !important; }
  .side { container-type: inline-size; }
  @container (max-width: 600px) { ha-card:not(.wide) .actions button { flex-basis: calc(50% - 5px); } }
  .checkpanel small.of { color: var(--secondary-text-color); font-size: .8em; text-transform: uppercase; letter-spacing: .04em; }
  .checkpanel h3 { margin: 0; font-size: 1.2em; font-weight: 500; }
  .checkpanel p { margin: 0; line-height: 1.45; }
  .checkpanel .big { display: flex; gap: 22px; }
  .checkpanel .big div { display: flex; flex-direction: column; }
  .checkpanel .big small { font-size: .75em; color: var(--secondary-text-color); }
  .checkpanel .big b { font-size: 1.8em; font-variant-numeric: tabular-nums; }
  .checkpanel ol { margin: 0; padding-left: 1.3em; }
  .checkpanel li.ok { color: #66bb6a; }
  .checkpanel li.ok::marker { content: "✓ "; }
  .checkpanel .hint { color: #ffb74d; min-height: 1.2em; }
  .checkpanel .res { padding: 10px 12px; border-radius: 10px; background: var(--secondary-background-color); }
  .checkpanel .res b { display: block; margin-bottom: 2px; }
  .res.pass b, .sum .pass { color: #66bb6a; } .res.warn b, .sum .warn { color: #ffb74d; }
  .res.fail b, .sum .fail { color: var(--error-color, #ef5350); } .res.skip b, .sum .skip { color: var(--secondary-text-color); }
  .checkpanel .btns { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 4px; }
  .checkpanel .btns button { flex: 1 1 40%; font: inherit; font-weight: 500; min-height: 48px; padding: 8px 14px; border-radius: 12px;
    cursor: pointer; border: 1px solid var(--divider-color); background: var(--secondary-background-color); color: var(--primary-text-color); }
  .checkpanel .btns button.primary { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
  .checkpanel .btns button.pulse { animation: glow 1.4s ease-in-out infinite; }
  @keyframes glow { 50% { box-shadow: 0 0 0 6px rgba(var(--rgb-primary-color, 3,169,244), .25); } }
  .sum { display: grid; grid-template-columns: 1fr auto; gap: 4px 12px; font-size: .92em; }
  .sug { margin-top: 12px; padding: 8px 12px; border-radius: 8px; background: var(--secondary-background-color); }
  .sug h4 { margin: 0 0 4px; }
  .sug ul { margin: 0; padding-left: 18px; }
  .sug p { margin: 0; }
  .sug .err { margin-top: 6px; color: var(--error-color, #db4437); }
  .sum span.v { grid-column: 1 / -1; color: var(--secondary-text-color); font-size: .88em; margin-top: -2px; }
  .empty { padding: 24px 16px; color: var(--secondary-text-color); }
`;

class TrikiCard extends HTMLElement {
  static getStubConfig() { return {}; }
  static getConfigElement() { return document.createElement("triki-card-editor"); }

  setConfig(config) {
    const was = this._config?.device_id;
    this._config = cardConfig(config);
    if (this._built) this._build();
    // a saved edit reaches a live card through setConfig: follow a new cap
    if (this._config.device_id !== was && (this._unsub || this._subscribing || this._empty)) {
      this._unsubscribe();
      this._deviceId = null;
      if (this.isConnected && this._hass) this._subscribe();
    }
  }

  getCardSize() { return 8; }
  getGridOptions() { return { columns: 12, min_columns: 6, rows: "auto" }; }

  set hass(hass) {
    this._hass = hass;
    // the profile language can change without a page reload: follow it, but
    // not in the middle of a check, which a rebuild would cut short
    const t = cardStrings(hass);
    const relang = this._t && t !== this._t && !this._chk;
    if (!this._t || relang) this._t = t;
    if (this._empty) { if (relang) this._noDevice(); }
    else if (!this._built || relang) this._build();
    else this._applyAdmin();
    if (this.isConnected && this._canSubscribe()) this._subscribe();
  }

  // a failed subscribe is retried by its own timer, not by every hass update
  _canSubscribe() { return !this._unsub && !this._subscribing && !this._retryTimer; }

  connectedCallback() {
    clearTimeout(this._teardownTimer);
    if (this._hass && this._canSubscribe()) this._subscribe();
    if (this._io) this._io.observe(this);
  }

  disconnectedCallback() {
    this._checkClose();
    this._unsubscribe();
    clearTimeout(this._retryTimer);
    this._retryTimer = null;
    clearInterval(this._dozeTimer);
    this._dozeTimer = null;
    if (this._io) this._io.disconnect();
    this._visible = false;
    // the browser keeps about 16 WebGL contexts: give this one back unless the
    // card was only moved (dashboard edit mode moves cards around)
    clearTimeout(this._teardownTimer);
    this._teardownTimer = setTimeout(() => { if (!this.isConnected) this._teardownScene(); }, 1000);
  }

  // ------------------------------------------------------------------ DOM
  _build() {
    const t = this._t || STRINGS.en;
    const c = this._config || {};
    // the renderer is bound to the canvas the new markup replaces
    this._teardownScene();
    if (this._io) this._io.disconnect();
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    const buttons = c.buttons || BUTTONS;
    const off = (name) => (buttons.includes(name) ? "" : " data-off");
    const axisRows = (id) => ["x", "y", "z"].map((a, i) =>
      `<div class="row"><span style="color:${AXIS_COLORS[i]}">${a}</span><div class="bar"><i id="${id}${a}" style="background:${AXIS_COLORS[i]}"></i></div><output id="${id}${a}v">—</output></div>`).join("");
    this.shadowRoot.innerHTML = `<style>${CSS}</style>
      <ha-card>
        <div class="head">
          <div class="name" id="name"></div>
          <div class="chip" id="state" data-chip="state"><div class="dot"></div><span id="stateText">${t.asleep}</span></div>
          <div class="chip" id="rateChip" data-chip="rate" hidden><ha-icon icon="mdi:sine-wave" style="--mdc-icon-size:14px"></ha-icon><span id="rate"></span></div>
          <div class="chip" id="rssiChip" data-chip="signal" hidden><ha-icon icon="mdi:bluetooth" style="--mdc-icon-size:14px"></ha-icon><span id="rssi"></span></div>
          <div class="chip check" id="checkChip" data-chip="state" hidden><ha-icon icon="mdi:clipboard-check-outline" style="--mdc-icon-size:14px"></ha-icon><span>${t.check.other}</span></div>
          <div class="chip" id="battChip" data-chip="battery" hidden><ha-icon id="battIcon" icon="mdi:battery" style="--mdc-icon-size:14px"></ha-icon><span id="batt"></span></div>
          <div class="chip" id="linkChip" data-chip="link" title="${t.linkq}" hidden><ha-icon icon="mdi:transfer" style="--mdc-icon-size:14px"></ha-icon><span id="link"></span></div>
        </div>
        <div class="tabs" id="tabs" hidden></div>
        <div class="body">
        <div class="stage asleep" id="stage">
          <canvas class="gl" id="gl"></canvas>
          <div class="angles">
            <div class="angle"><small>${t.roll}</small><b id="roll">—</b></div>
            <div class="angle"><small>${t.pitch}</small><b id="pitch">—</b></div>
            <div class="angle"><small>${t.yaw}</small><b id="yaw">—</b></div>
          </div>
          <div class="btn-ind" id="btnInd"><div class="led"></div>${t.button}</div>
          <div class="toast" id="toast"></div>
          <div class="sleep" id="sleepText">${t.wake}</div>
          <div class="headhint" id="headHint" hidden>${t.heading}</div>
          <div class="checkbar" id="checkBar"><b id="checkBarText"></b><div class="time"><i id="checkTime"></i></div></div>
          <div class="wizard" id="wizard">
            <div class="find" id="wizFind" hidden><span class="pic"><img src="${asset("tex_resin.webp")}" alt=""><i></i></span><p id="wizFindText"></p></div>
            <p id="wizText"></p>
            <div class="logo-match" id="wizLogo" hidden>
              <figure><img src="${asset("tex_resin.webp")}" alt=""><figcaption>${t.cal.resin}</figcaption></figure>
              <span class="arrow">⟲</span>
              <figure><img id="wizMetal" src="${asset("tex_metal.webp")}" alt=""><figcaption>${t.cal.metal}</figcaption></figure>
            </div>
            <div class="slider" id="wizSlider" hidden>
              <button id="wizLeft" aria-label="-15°">↺</button>
              <input type="range" id="wizAngle" min="-180" max="180" step="5" value="0">
              <button id="wizRight" aria-label="+15°">↻</button>
              <output id="wizAngleOut">0°</output>
            </div>
            <div class="err" id="wizErr"></div>
            <div class="row"><button id="wizCancel">${t.cal.cancel}</button><button class="primary" id="wizNext">${t.cal.next}</button></div>
          </div>
        </div>
        <div class="side">
        <div class="checkpanel" id="checkPanel"></div>
        ${c.show_values ? `<div class="values"><div><h4>${t.gyro}</h4>${axisRows("g")}</div><div><h4>${t.accel}</h4>${axisRows("a")}</div></div>` : ""}
        ${c.show_history ? `<div class="chart"><small>${t.gyro} · ${t.history}</small><canvas class="hist" id="hist"></canvas></div>` : ""}
        ${c.show_gestures ? `<div class="glist" id="glist"><small>${t.glist.title}</small><div class="gitems">${GESTURES.map(([id]) =>
          `<button class="gitem" data-g="${id}">${t.glist[id] || t.gestures[id]}</button>`).join("")}</div><p class="ghow" id="ghow">${t.glist.hint}</p></div>` : ""}
        <div class="actions"${c.buttons.length ? "" : ' style="display:none"'}>
          <button id="cal" disabled${off("calibrate")}><ha-icon icon="mdi:target"></ha-icon><span class="lbl">${t.calibrate}</span></button>
          <button id="reset" disabled${off("align")}><ha-icon icon="mdi:compass-outline"></ha-icon><span class="lbl">${t.reset}</span></button>
          <button id="led" disabled${off("led")}><ha-icon icon="mdi:led-on"></ha-icon><span class="lbl">${t.led}</span></button>
          <button id="check"${off("check")}><ha-icon icon="mdi:clipboard-check-outline"></ha-icon><span class="lbl">${t.check.open}</span></button>
        </div>
        <div class="help"${c.show_help && (c.show_model || c.buttons.length) ? "" : ' style="display:none"'}>${c.show_model ? `<div class="front"><span class="pic"><img src="${asset("tex_resin.webp")}" alt=""><i></i></span><p>${t.help.mark}</p></div>` : ""}${[["calibrate", "cal"], ["align", "align"], ["led", "led"], ["check", "check"]]
          .filter(([b]) => c.buttons.includes(b)).map(([b, k]) => `<p data-for="${b}">${t.help[k]}</p>`).join("")}</div>
        </div>
        </div>
      </ha-card>`;
    const $ = (id) => this.shadowRoot.getElementById(id);
    const card = this.shadowRoot.querySelector("ha-card");
    card.classList.toggle("nomodel", c.show_model === false);
    for (const chip of card.querySelectorAll(".head [data-chip]")) {
      chip.toggleAttribute("data-off", !c.chips.includes(chip.dataset.chip));
    }
    this._wideRo?.disconnect();
    this._wideRo = new ResizeObserver(() => card.classList.toggle("wide", this.clientWidth >= 760));
    this._wideRo.observe(this);
    this._el = {
      name: $("name"), state: $("state"), stateText: $("stateText"), rate: $("rate"), rateChip: $("rateChip"),
      rssi: $("rssi"), rssiChip: $("rssiChip"), link: $("link"), linkChip: $("linkChip"), batt: $("batt"), battChip: $("battChip"), battIcon: $("battIcon"),
      stage: $("stage"), gl: $("gl"), roll: $("roll"), pitch: $("pitch"), yaw: $("yaw"), btnInd: $("btnInd"),
      toast: $("toast"), tabs: $("tabs"), sleepText: $("sleepText"), headHint: $("headHint"), hist: $("hist"), reset: $("reset"), led: $("led"),
      cal: $("cal"), wizard: $("wizard"), wizText: $("wizText"), wizFind: $("wizFind"), wizFindText: $("wizFindText"), wizErr: $("wizErr"),
      wizNext: $("wizNext"), wizCancel: $("wizCancel"),
      wizLogo: $("wizLogo"), wizSlider: $("wizSlider"), wizMetal: $("wizMetal"), wizAngle: $("wizAngle"),
      wizAngleOut: $("wizAngleOut"), wizLeft: $("wizLeft"), wizRight: $("wizRight"),
      check: $("check"), checkPanel: $("checkPanel"), checkBar: $("checkBar"), checkBarText: $("checkBarText"),
      checkTime: $("checkTime"), checkChip: $("checkChip"), card,
    };
    for (const p of ["g", "a"]) for (const a of ["x", "y", "z"]) {
      this._el[`${p}${a}`] = $(`${p}${a}`);
      this._el[`${p}${a}v`] = $(`${p}${a}v`);
    }
    for (const b of this.shadowRoot.querySelectorAll(".gitem")) {
      b.addEventListener("click", () => this._pickGesture(b.dataset.g));
    }
    this._el.name.textContent = c.title || "Triki"; // text, not markup
    this._el.reset.addEventListener("click", () => this._wizard("heading"));
    this._el.led.addEventListener("click", () => this._toggleLed());
    this._el.cal.addEventListener("click", () => this._wizard("flat"));
    this._el.check.addEventListener("click", () => this._checkOpen());
    this._applyAdmin();
    this._el.wizCancel.addEventListener("click", () => this._wizard(null));
    this._el.wizNext.addEventListener("click", () => this._wizardNext());
    this._el.wizAngle.addEventListener("input", () => this._previewLogo(+this._el.wizAngle.value));
    this._el.wizLeft.addEventListener("click", () => this._previewLogo(+this._el.wizAngle.value - 15));
    this._el.wizRight.addEventListener("click", () => this._previewLogo(+this._el.wizAngle.value + 15));
    this._history = [];
    this._built = true;
    this._io = new IntersectionObserver((entries) => {
      this._visible = entries.some((e) => e.isIntersecting);
      if (this._visible) this._startRender();
    });
    if (this.isConnected) this._io.observe(this);
    if (this._status) this._showStatus(this._status);
  }

  // ------------------------------------------------------------------ data
  async _subscribe() {
    this._subscribing = true;
    // a newer subscribe, an unsubscribe or a removed card makes this one stale
    const gen = this._subGen = (this._subGen || 0) + 1;
    const stale = () => gen !== this._subGen || !this.isConnected;
    let unsubs = [];
    const drop = () => { for (const u of unsubs) u().catch?.(() => {}); };
    try {
      // a fixed token from the config, otherwise every token: the card then shows
      // whichever one is awake (a home can have several, most of them asleep)
      let ids = this._config?.device_id ? [this._config.device_id] : null;
      let names = this._names;
      if (!ids) {
        const devices = await this._hass.connection.sendMessagePromise({ type: "triki/devices" });
        if (stale()) return;
        ids = devices.map((d) => d.device_id);
        // none loaded yet (Home Assistant still starting, an entry reloading)
        if (!ids.length) { this._lost(); return; }
        names = Object.fromEntries(devices.map((d) => [d.device_id, d.name]));
      }
      const results = await Promise.allSettled(ids.map((id) => this._hass.connection.subscribeMessage(
        (msg) => this._onMessage(id, msg), { type: "triki/subscribe", device_id: id })));
      unsubs = results.filter((r) => r.status === "fulfilled").map((r) => r.value);
      if (stale()) { drop(); return; }
      const failed = results.find((r) => r.status === "rejected");
      if (failed) throw failed.reason; // all or none: the rest are dropped and retried
      this._names = names;
      this._ids = ids;
      this._statuses = {};
      // the pick is per browser: "auto" follows the awake token, an id pins one
      const stored = this._config?.device_id ? null : localStorage.getItem(PICK_KEY);
      this._pick = stored && ids.includes(stored) ? stored : "auto";
      this._deviceId = this._pick !== "auto" ? this._pick
        : this._deviceId && ids.includes(this._deviceId) ? this._deviceId : ids[0];
      this._unsubs = unsubs;
      this._unsub = () => Promise.all(unsubs.map((u) => u()));
      this._retryDelay = 0;
      this._reloadSince = null;
      if (this._empty) { this._empty = false; this._build(); }
      this._renderTabs();
    } catch (err) {
      drop();
      if (stale()) return;
      console.warn("triki-card: subscribe failed", err);
      this._lost();
    } finally {
      if (gen === this._subGen) this._subscribing = false;
    }
  }

  _unsubscribe() {
    this._subGen = (this._subGen || 0) + 1; // a subscribe in flight is dropped
    this._subscribing = false;
    if (this._unsub) { this._unsub().catch?.(() => {}); this._unsub = null; }
  }

  // Try again later, backing off to a minute: Home Assistant may still be
  // starting, or an entry reloading, which is not worth a request per hass update.
  _retrySoon(delay) {
    if (this._retryTimer || !this.isConnected) return;
    this._retryDelay = delay ?? Math.min(60000, (this._retryDelay || 1000) * 2);
    this._retryTimer = setTimeout(() => {
      this._retryTimer = null;
      if (this.isConnected && this._hass && !this._unsub && !this._subscribing) this._subscribe();
    }, this._retryDelay);
  }

  // No cap to show. Right after a reload of the integration that is expected for
  // a few seconds: the card keeps its last look meanwhile instead of blinking.
  _lost() {
    const reloading = this._built && this._reloadSince && Date.now() - this._reloadSince < 30000;
    if (!reloading) this._noDevice();
    this._retrySoon();
  }

  // The integration reloaded (its options changed): subscribe to the new device
  // objects once they are up.
  _resubscribeSoon() {
    this._unsubscribe();
    this._reloadSince ??= Date.now();
    this._retryDelay = 0;
    this._retrySoon(2000);
  }

  _isLive(s) { return !!(s && s.connected && s.streaming); }

  // Follow the awake token: switch when the shown one is not live and another is.
  _follow(id) {
    if (id === this._deviceId || this._config?.device_id || this._pick !== "auto" || this._chk) return;
    if (this._isLive(this._statuses[this._deviceId]) || !this._isLive(this._statuses[id])) return;
    this._show(id);
  }

  _show(id) {
    this._deviceId = id;
    this._target = null;
    this._history = [];
    this._historyDirty = true;
    if (this._statuses[id]) this._showStatus(this._statuses[id]);
    this._renderTabs();
  }

  _choose(pick) {
    this._pick = pick;
    if (pick === "auto") localStorage.removeItem(PICK_KEY); else localStorage.setItem(PICK_KEY, pick);
    if (pick !== "auto") { this._show(pick); return; }
    const live = this._ids.find((id) => this._isLive(this._statuses[id]));
    this._show(live || this._deviceId);
  }

  // One tab per token plus "Auto", only when there is more than one token.
  _renderTabs() {
    const el = this._el?.tabs;
    if (!el) return;
    const ids = this._ids || [];
    el.hidden = ids.length < 2 || !!this._config?.device_id;
    if (el.hidden) return;
    const t = this._t || STRINGS.en;
    const tab = (pick, label, live) => {
      const sel = this._pick === pick;
      return `<button class="tab${sel ? " sel" : ""}" data-pick="${pick}">${
        live === undefined ? "" : `<span class="dot${live ? " live" : ""}"></span>`}${label}</button>`;
    };
    el.innerHTML = tab("auto", t.auto) + ids.map((id) => tab(
      id, (this._statuses[id]?.name || this._names?.[id] || id).replace(/[<>&"]/g, ""),
      this._isLive(this._statuses[id]))).join("");
    for (const b of el.querySelectorAll(".tab")) b.addEventListener("click", () => this._choose(b.dataset.pick));
  }

  // replaces the card's body: the built card is gone until a cap is found
  _noDevice() {
    this._teardownScene();
    if (this._io) this._io.disconnect();
    this._empty = true;
    this._built = false;
    const card = this.shadowRoot?.querySelector("ha-card");
    if (card) card.innerHTML = `<div class="empty">${(this._t || STRINGS.en).nodevice}</div>`;
  }

  _onMessage(id, msg) {
    if (msg.type === "reload") { this._resubscribeSoon(); return; }
    if (msg.type === "status") {
      const was = this._isLive(this._statuses[id]);
      this._statuses[id] = msg;
      if (was !== this._isLive(msg) || !this._tabsDrawn) { this._tabsDrawn = true; this._renderTabs(); }
      this._follow(id);
    }
    else if (msg.type === "motion") this._follow(id);
    if (this._chk) this._checkMessage(id, msg);
    if (id !== this._deviceId) return;
    if (msg.type === "status") this._showStatus(msg);
    else if (msg.type === "motion") this._showMotion(msg);
    else if (msg.type === "event") this._showEvent(msg.event, msg.data);
  }

  _showDoze() {
    const t = this._t, el = this._el;
    if (!el) return;
    const left = this._dozeUntil == null ? 0 : Math.round((this._dozeUntil - Date.now()) / 1000);
    el.sleepText.textContent = left > 0 ? t.dozeHint.replace("{n}", left) : t.dozeLate;
  }

  _showStatus(s) {
    this._status = s;
    const t = this._t, el = this._el;
    if (!el) return;
    if (!this._config?.title && s.name) el.name.textContent = s.name;
    const live = s.connected && s.streaming;
    el.state.className = `chip ${live ? "live" : s.unresponsive ? "warn" : ""}`;
    // readiness: since 0.3.0; waiting_for_sleep alone stayed true until the next wake
    const dozing = s.readiness ? s.readiness === "dozing" : !s.connected && s.waiting_for_sleep;
    el.stateText.textContent = live ? t.streaming : s.connected ? t.connected
      : s.unresponsive ? t.unresponsive : dozing ? t.dozing : t.asleep;
    this._dozeUntil = dozing && s.doze_left_s != null ? Date.now() + s.doze_left_s * 1000 : null;
    clearInterval(this._dozeTimer);
    this._dozeTimer = dozing ? setInterval(() => this._showDoze(), 1000) : null;
    if (dozing) this._showDoze();
    else el.sleepText.textContent = t.wake;
    el.stage.classList.toggle("asleep", !live);
    // only with a way to fix it on the card: the Align direction button
    el.headHint.hidden = !(live && s.heading_known === false && (this._config?.buttons || BUTTONS).includes("align"));
    el.rateChip.hidden = !live;
    if (live) el.rate.textContent = `${Math.round(s.measured_rate ?? s.rate ?? 0)} ${t.rate}`;
    el.rssiChip.hidden = s.rssi == null;
    if (s.rssi != null) el.rssi.textContent = `${s.rssi} dBm`;
    el.linkChip.hidden = s.link_quality == null;
    if (s.link_quality != null) el.link.textContent = `${Math.round(s.link_quality)}%`;
    el.battChip.hidden = s.battery == null;
    if (s.battery != null) {
      el.batt.textContent = `${s.battery}%`;
      const step = Math.max(1, Math.min(10, Math.round(s.battery / 10))) * 10;
      el.battIcon.setAttribute("icon", step >= 100 ? "mdi:battery" : `mdi:battery-${step}`);
    }
    el.reset.disabled = !live;
    el.cal.disabled = !live;
    el.checkChip.hidden = !(s.checking && !this._chk);
    el.check.disabled = !!s.checking && !this._chk;
    if (!live && (this._wizStep === "flat" || this._wizStep === "heading")) this._wizard(null);
    this._markGestures();
    el.led.disabled = !s.connected;
    el.led.classList.toggle("on", !!s.led);
    el.btnInd.classList.toggle("on", !!s.button);
    this._setModelState(s.led, s.button);
    if (!live) {
      this._target = null;
      for (const k of ["roll", "pitch", "yaw"]) el[k].textContent = "—";
    }
  }

  // Left-right from the side that is up: the integration measures it from the
  // green side, so a cap lying metal up read ±180°. Past 100° the other side
  // counts as up, and back below 80° (no flicker on the edge).
  _faceRoll(roll) {
    const a = Math.abs(roll);
    if (a > 100) this._capUp = true;
    else if (a < 80) this._capUp = false;
    if (!this._capUp) return roll;
    return roll > 0 ? roll - 180 : roll + 180;
  }

  _showMotion(m) {
    const el = this._el;
    if (!el) return;
    const [w, x, y, z] = m.quaternion;
    this._target = [w, x, y, z];
    el.roll.textContent = `${Math.round(this._faceRoll(m.euler[0]))}°`;
    el.pitch.textContent = `${Math.round(m.euler[1])}°`;
    el.yaw.textContent = `${Math.round(m.euler[2])}°`;
    el.btnInd.classList.toggle("on", !!m.button);
    this._setModelState(this._status?.led, m.button);
    if (this._config.show_values) {
      ["x", "y", "z"].forEach((a, i) => {
        this._bar(el[`g${a}`], m.gyro[i] / GYRO_RANGE);
        el[`g${a}v`].textContent = m.gyro[i].toFixed(0);
        this._bar(el[`a${a}`], m.accel[i] / ACCEL_RANGE);
        el[`a${a}v`].textContent = m.accel[i].toFixed(2);
      });
    }
    if (this._config.show_history) {
      const now = performance.now() / 1000;
      this._history.push([now, ...m.gyro]);
      while (this._history.length && now - this._history[0][0] > HISTORY_S) this._history.shift();
      this._historyDirty = true;
    }
    this._startRender();
  }

  // the LED glow and the pressed button on the procedural model
  _setModelState(led, pressed) {
    if (!this._cap) return;
    const logo = this._status?.logo_angle ?? 0;
    if (logo !== this._capLogo && this._wizStep !== "logo") {
      this._capLogo = logo;
      this._setLogo(logo);
    }
    const key = `${!!led}${!!pressed}`;
    if (key === this._capState) return;
    this._capState = key;
    this._cap.setLed(!!led);
    this._cap.setPressed(!!pressed);
    this._needsFrame = true;
    this._startRender();
  }

  _bar(i, v) {
    const f = Math.max(-1, Math.min(1, v));
    i.style.width = `${Math.abs(f) * 50}%`;
    i.style.left = f < 0 ? `${50 + f * 50}%` : "50%";
  }

  // ------------------------------------------------------------------ gesture list
  _gestureOn(id) {
    const opt = GESTURES.find((g) => g[0] === id)?.[2];
    const o = this._status?.options;
    return !opt || !o || o[opt] !== false; // an older integration sends no options
  }

  _pickGesture(id) {
    const t = this._t.glist, how = this.shadowRoot.getElementById("ghow");
    if (!how) return;
    this._gSel = this._gSel === id ? null : id;
    for (const b of this.shadowRoot.querySelectorAll(".gitem")) b.classList.toggle("sel", b.dataset.g === this._gSel);
    how.textContent = !this._gSel ? t.hint
      : t.how[id] + (this._gestureOn(id) ? "" : ` (${t.off})`);
  }

  _markGestures() {
    for (const b of this.shadowRoot.querySelectorAll(".gitem")) {
      const on = this._gestureOn(b.dataset.g);
      b.classList.toggle("off", !on);
      b.title = on ? this._t.glist.how[b.dataset.g] : this._t.glist.off;
    }
    if (this._gSel) { const id = this._gSel; this._gSel = null; this._pickGesture(id); }
  }

  _lightGesture(kind) {
    const g = GESTURES.find((x) => x[1].includes(kind));
    const b = g && this.shadowRoot.querySelector(`.gitem[data-g="${g[0]}"]`);
    if (!b) return;
    b.classList.add("hit");
    clearTimeout(b._hit);
    b._hit = setTimeout(() => b.classList.remove("hit"), 900);
  }

  _showEvent(kind, data) {
    this._lightGesture(kind);
    const names = this._t.gestures;
    let label = names[kind];
    if (!label) return;
    if ((kind === "rotate_cw" || kind === "rotate_ccw") && data?.steps) label += ` ×${data.steps}`;
    if (kind === "motion") return; // too frequent to be worth a toast
    const st = this._el.stage;
    st.classList.remove("bump");
    void st.offsetWidth; // restart the animation
    st.classList.add("bump");
    const el = this._el.toast;
    el.textContent = label;
    el.classList.add("show");
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => el.classList.remove("show"), 1200);
  }

  // Calibration: flat (levels the cap, zeroes the heading), then logo (the metal logo's
  // angle against the PCB, matched by eye: the crown is crimped on at any angle).
  _wizard(step) {
    const el = this._el, t = this._t.cal;
    if (this._wizStep === "logo" && step !== "logo") this._setLogo(this._status?.logo_angle); // undo preview
    this._wizStep = step;
    el.wizard.classList.toggle("show", !!step);
    el.card?.classList.toggle("calibrating", !!step);
    el.wizErr.textContent = "";
    if (!step) return;
    el.wizText.textContent = t[step];
    el.wizFind.hidden = step === "logo";
    el.wizFindText.textContent = t.find;
    el.wizLogo.hidden = el.wizSlider.hidden = step !== "logo";
    el.wizCancel.textContent = step === "logo" ? t.skip : t.cancel;
    if (step === "logo") this._previewLogo(this._status?.logo_angle ?? 0);
  }

  // degrees, clockwise on screen: the picture and the model turn together
  _previewLogo(deg) {
    deg = ((Math.round(deg) + 540) % 360) - 180;
    const el = this._el;
    el.wizAngle.value = deg;
    el.wizAngleOut.textContent = `${deg}°`;
    el.wizMetal.style.transform = `rotate(${deg}deg)`;
    this._setLogo(deg);
  }

  _setLogo(deg) {
    if (!this._cap) return;
    this._cap.setLogoAngle(deg ?? 0);
    this._needsFrame = true;
    this._startRender();
  }

  async _wizardNext() {
    const step = this._wizStep;
    const t = this._t.cal;
    try {
      if (step === "heading") {
        await this._hass.connection.sendMessagePromise({ type: "triki/reset_heading", device_id: this._deviceId });
        this._wizard(null);
        this._toast(t.turned);
        return;
      }
      const msg = { type: "triki/calibrate", device_id: this._deviceId, step };
      if (step === "logo") msg.angle = +this._el.wizAngle.value;
      await this._hass.connection.sendMessagePromise(msg);
      if (step === "flat") { this._wizard("logo"); return; }
      this._wizStep = null; // keep the angle just saved on the model
      this._wizard(null);
      this._toast(t.saved);
    } catch (err) {
      // home-assistant-js-websocket rejects with the error object ({code, message})
      const e = err?.error || err;
      this._el.wizErr.textContent = t.err[e?.code] || e?.message || t.err.no_data;
    }
  }

  _toast(text) {
    const el = this._el.toast;
    el.textContent = text;
    el.classList.add("show");
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => el.classList.remove("show"), 1500);
  }

  _toggleLed() {
    const ent = Object.values(this._hass.entities || {}).find(
      (e) => e.device_id === this._deviceId && e.entity_id.startsWith("switch.") && e.translation_key === "led");
    if (!ent) return;
    this._hass.callService("switch", this._status?.led ? "turn_off" : "turn_on", { entity_id: ent.entity_id });
  }

  // ------------------------------------------------------------------ guided check
  // Only an admin may calibrate or run the check (the server refuses others too).
  _applyAdmin() {
    const admin = this._hass?.user ? !!this._hass.user.is_admin : true;
    if (!this._el) return;
    this._el.check.hidden = !admin;
    this._el.cal.hidden = !admin;
    for (const p of this.shadowRoot.querySelectorAll('.help [data-for="calibrate"], .help [data-for="check"]')) p.hidden = !admin;
  }

  _fmt(text, values = {}) {
    const esc = (x) => String(x).replace(/[<>&"]/g, (c) => `&#${c.charCodeAt(0)};`);
    return String(text || "").replace(/\{(\w+)\}/g, (_, k) => esc(values[k] ?? "—"));
  }

  _send(msg) { return this._hass.connection.sendMessagePromise(msg); }

  // Every token the card shows gets a check started at once, so the press that picks
  // one does not reach automations; the others are released as soon as one is picked.
  async _checkOpen() {
    if (this._chk) return;
    const ids = this._config?.device_id ? [this._config.device_id] : (this._ids || []);
    if (!ids.length) return;
    const session = (crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`).replace(/[^\w-]/g, "");
    const chk = { session, owned: new Set(), id: null, run: null, msg: null };
    this._chk = chk;
    this._wizard(null);
    this._el.card.classList.add("checking");
    const results = await Promise.allSettled(ids.map((id) =>
      this._send({ type: "triki/check", action: "start", device_id: id, session }).then(() => id)));
    if (this._chk !== chk) { // closed meanwhile: do not leave the started ones running
      for (const r of results) if (r.status === "fulfilled") {
        this._send({ type: "triki/check", action: "stop", device_id: r.value, session }).catch(() => {});
      }
      return;
    }
    for (const r of results) if (r.status === "fulfilled") chk.owned.add(r.value);
    if (!chk.owned.size) { chk.msg = "busy"; this._renderCheck(true); return; }
    chk.renew = setInterval(() => this._checkRenew(), CHECK_RENEW_MS);
    chk.timer = setInterval(() => this._checkTick(), 250);
    // no need to ask when the card is pinned to one token or holds only one
    const pinned = this._pick !== "auto" && chk.owned.has(this._pick) ? this._pick : null;
    if (pinned || chk.owned.size === 1) await this._checkChoose(pinned || [...chk.owned][0]);
    else this._renderCheck(true);
  }

  async _checkRenew() {
    const chk = this._chk;
    if (!chk) return;
    const ids = chk.id ? [chk.id] : [...chk.owned];
    for (const id of ids) {
      try {
        await this._send({ type: "triki/check", action: "start", device_id: id, session: chk.session });
      } catch (err) {
        if ((err?.error || err)?.code === "busy" && id === chk.id) { chk.msg = "busy"; this._renderCheck(true); }
      }
    }
  }

  async _checkChoose(id) {
    const chk = this._chk;
    if (!chk || chk.id) return;
    chk.id = id;
    for (const other of chk.owned) {
      if (other !== id) this._send({ type: "triki/check", action: "stop", device_id: other, session: chk.session }).catch(() => {});
    }
    chk.owned = new Set([id]);
    if (id !== this._deviceId) this._show(id);
    const { CheckRun } = await loadCheck();
    if (this._chk !== chk) return;
    const status = this._statuses?.[id] || this._status || {};
    chk.run = new CheckRun({ options: status.options || {} });
    chk.run.feedStatus(status);
    this._renderCheck(true);
  }

  _checkMessage(id, msg) {
    const chk = this._chk;
    if (!chk.id) {
      // picking: the first press on a token this card holds a check for
      if (msg.type === "event" && chk.owned.has(id) && ["press", "wake", "double_press", "long_press"].includes(msg.event)) {
        this._checkChoose(id);
      } else if (msg.type === "status") this._renderCheck();
      return;
    }
    if (id !== chk.id || !chk.run) return;
    const run = chk.run;
    if (msg.type === "status") run.feedStatus(msg);
    else if (msg.type === "motion") run.feedMotion(msg);
    else if (msg.type === "event") run.feedEvent(msg.event, msg.data || {});
    this._renderCheck();
  }

  _checkTick() {
    const run = this._chk?.run;
    if (!run) return;
    run.tick();
    this._renderCheck();
  }

  async _checkAction(action) {
    const chk = this._chk, run = chk?.run;
    if (action === "close") { this._checkClose(); return; }
    if (action.startsWith("pick:")) { this._checkChoose(action.slice(5)); return; }
    if (!run) return;
    const t = this._t.check;
    if (action === "apply") {
      // only what the check suggested, each with the options form's limits (server side)
      const options = Object.fromEntries(run.suggestions().map((g) => [g.key, g.value]));
      try {
        await this._send({ type: "triki/apply", device_id: chk.id, options });
        chk.applied = true;
        chk.err = "";
      } catch (err) {
        const e = err?.error || err;
        chk.err = this._fmt(t.sug.err, { e: e?.message || e?.code || "?" });
      }
      this._renderCheck(true);
      return;
    }
    if (action === "start") {
      if (run.start()) {
        chk.ref = this._target ? [...this._target] : null; // the hint moves from here
        chk.err = "";
        if (run.step.id === "sleep") {
          // the server drops the link as after idling; the step follows the status
          try {
            await this._send({ type: "triki/check", action: "sleep", device_id: chk.id, session: chk.session });
          } catch (err) {
            const e = err?.error || err;
            chk.err = e?.message || e?.code || "?";
            run.redo();
          }
        }
      }
    } else if (action === "done") {
      if (run.step.external) {
        // the flat calibration is the existing server step; its errors stay on this step
        try {
          await this._send({ type: "triki/calibrate", device_id: chk.id, step: "flat" });
          run.complete({ status: "pass" });
          chk.err = "";
        } catch (err) {
          const e = err?.error || err;
          chk.err = this._t.cal.err[e?.code] || e?.message || this._t.cal.err.no_data;
        }
      } else run.done();
    } else if (action === "redo") { run.redo(); chk.err = ""; }
    else if (action === "skip") { run.skip(); chk.err = ""; }
    else if (action === "next") run.next();
    this._renderCheck(true);
  }

  // The summary measures nothing: let the token go back to automations and idle
  // timers now, not when the card is closed (a background tab keeps it open).
  _checkRelease(chk) {
    chk.released = true;
    clearInterval(chk.renew);
    for (const id of chk.owned) {
      this._send({ type: "triki/check", action: "stop", device_id: id, session: chk.session }).catch(() => {});
    }
  }

  _checkClose() {
    const chk = this._chk;
    if (!chk) return;
    this._chk = null;
    clearInterval(chk.renew);
    clearInterval(chk.timer);
    if (!chk.released) for (const id of chk.owned) {
      this._send({ type: "triki/check", action: "stop", device_id: id, session: chk.session }).catch(() => {});
    }
    this._el?.card.classList.remove("checking");
    this._setGhost(null);
    if (this._status) this._showStatus(this._status);
  }

  // The panel is rebuilt when the step, phase or result changes; numbers in between.
  _renderCheck(force = false) {
    const chk = this._chk, el = this._el;
    if (!chk || !el) return;
    const t = this._t.check;
    const run = chk.run;
    const v = run ? run.view() : null;
    if (v?.finished && !chk.released) this._checkRelease(chk);
    const key = !run ? `pick|${chk.msg}|${[...chk.owned].map((id) => this._isLive(this._statuses?.[id])).join()}`
      : v.finished ? "summary" : `${v.id}|${v.phase}|${v.online}|${v.result?.status}|${chk.err}`;
    if (force || key !== chk.key) {
      chk.key = key;
      el.checkPanel.innerHTML = this._checkHtml(v);
      for (const b of el.checkPanel.querySelectorAll("button[data-a]")) {
        b.addEventListener("click", () => this._checkAction(b.dataset.a));
      }
    }
    // live numbers
    const live = v && !v.finished ? v.live : {};
    const set = (id, text) => { const n = el.checkPanel.querySelector(`#${id}`); if (n) n.textContent = text; };
    if (v && !v.finished) {
      if (v.id === "turn_cw" || v.id === "turn_ccw") {
        set("cSteps", live.expected != null ? `${live.steps} / ${live.expected}` : `${live.steps}`);
        set("cAngle", `${live.angle}°`);
        set("cWrong", live.wrong ? `${live.wrong} ${t.wrong}` : "");
      }
      if (v.id === "tilt") set("cHint", live.hint ? t.reason[live.hint] : "");
      if (v.id === "flip") set("cHint", t.flipStage[live.stage] || "");
      if (v.id === "press") {
        set("cHint", live.hint ? this._fmt(t.reason.wrong_press, {
          got: this._t.gestures[live.hint.got] || live.hint.got, want: this._t.gestures[live.hint.want] || live.hint.want }) : "");
        el.checkPanel.querySelectorAll("li").forEach((li, i) => li.classList.toggle("ok", i < live.got));
      }
      if ((v.id === "rest" || v.id === "drift") && live.moved) set("cHint", t.reason.moved);
      if (["tap", "shake", "throw", "lean", "handle"].includes(v.id)) set("cCount", `${live.count} / ${live.want}`);
      if (v.id === "shake") set("cHint", live.tries > live.count ? this._fmt(t.tries, { n: live.tries }) : "");
      if (v.id === "sleep" && v.phase === "running") {
        set("cHint", this._fmt(t.sleepStage[live.stage] || "", { left: live.left ?? "—" }));
      }
      if (v.id === "lean") set("cHint", live.hint ? t.reason[live.hint] : "");
      if (v.extra && v.phase === "running") {
        const list = Object.entries(v.extra).map(([k, n]) => `${this._t.gestures[k] || k} ×${n}`).join(", ");
        set("cHint", this._fmt(t.reason.extra, { extra: list }));
      }
      el.checkBarText.textContent = `${t.steps[v.id]}${v.phase === "running" && v.limit ? ` · ${Math.max(0, Math.ceil(v.limit - v.elapsed))} ${t.sec}` : ""}`;
      el.checkTime.style.width = v.phase === "running" && v.limit ? `${Math.min(100, (v.elapsed / v.limit) * 100)}%` : "0";
    } else {
      el.checkBarText.textContent = run ? t.summary : t.title;
      el.checkTime.style.width = "0";
    }
    // shown before Start too, so the move is seen before it is asked for
    this._setGhost(v && !v.finished && (v.phase === "running" || v.phase === "ready") ? v : null);
  }

  _checkHtml(v) {
    const t = this._t.check, chk = this._chk;
    const btn = (a, label, cls = "") => `<button data-a="${a}" class="${cls}">${label}</button>`;
    if (chk.msg === "busy") {
      return `<h3>${t.title}</h3><p>${t.busy}</p><div class="btns">${btn("close", t.close)}</div>`;
    }
    if (!v) {
      const caps = [...chk.owned].map((id) => {
        const st = this._statuses?.[id];
        const dot = `<span class="dot ${this._isLive(st) ? "on" : ""}"></span>`;
        return btn(`pick:${id}`, `${dot}${this._fmt("{n}", { n: st?.name || id })}`);
      }).join("");
      return `<small class="of">${t.title}</small><h3>${t.pick}</h3>
        <p>${t.text.identify}</p><div class="btns">${caps}${btn("close", t.close)}</div>`;
    }
    if (v.finished) {
      const rows = chk.run.steps.map((s) => {
        const r = v.results[s.id] || { status: "skip" };
        const detail = this._resultText(s.id, r);
        return `<span>${t.steps[s.id]}</span><b class="${r.status}">${t.status[r.status]}</b>${detail ? `<span class="v">${detail}</span>` : ""}`;
      }).join("");
      const sugs = chk.applied ? [] : chk.run.suggestions();
      let sug = "";
      if (chk.applied) sug = `<div class="sug"><p>${t.sug.applied}</p></div>`;
      else if (sugs.length) {
        const items = sugs.map((g) => `<li>${this._fmt(t.sug[g.key], g)}</li>`).join("");
        sug = `<div class="sug"><h4>${t.sug.title}</h4><ul>${items}</ul><p><small>${t.sug.note}</small></p>${chk.err ? `<p class="err">${chk.err}</p>` : ""}</div>`;
      }
      const btns = sugs.length ? btn("apply", t.sug.apply, "primary") + btn("close", t.close) : btn("close", t.close, "primary");
      return `<small class="of">${t.title}</small><h3>${t.summary}</h3><div class="sum">${rows}</div>${sug}
        <details class="report"><summary>${t.report}</summary><textarea readonly rows="9">${this._fmt("{r}", { r: chk.run.report({ version: VERSION }) })}</textarea></details>
        <div class="btns">${btns}</div>`;
    }
    const of = this._fmt(t.stepOf, { n: v.index + 1, total: v.total });
    let body = `<p>${t.text[v.id]}</p>`;
    if ((v.id === "turn_cw" || v.id === "turn_ccw") && !chk.run.options.knob) body += `<p><small>${t.text.knobOff}</small></p>`;
    if (v.id === "press") {
      body = `<p>${t.text.press}</p><ol>${v.live.want.map((k) => `<li>${this._t.gestures[k] || k}</li>`).join("")}</ol>`;
    }
    let live = "";
    if (v.id === "turn_cw" || v.id === "turn_ccw") {
      live = `<div class="big"><div><small>${t.count}</small><b id="cSteps">0</b></div><div><small>${t.angle}</small><b id="cAngle">0°</b></div></div><div class="hint" id="cWrong"></div>`;
    } else if (["tap", "shake", "throw", "lean", "handle"].includes(v.id)) {
      const label = { lean: t.leans, shake: t.recognised, handle: t.lifts }[v.id] || t.times;
      live = `<div class="big"><div><small>${label}</small><b id="cCount">0 / ${v.live.want}</b></div></div><div class="hint" id="cHint"></div>`;
    } else if (["tilt", "flip", "press", "rest", "drift", "sleep"].includes(v.id)) {
      live = `<div class="hint" id="cHint"></div>`;
    }
    let res = "", btns = "";
    if (v.phase === "paused") {
      res = `<div class="res warn"><b>${t.paused}</b></div>`;
      btns = btn("skip", t.skip) + btn("close", t.close);
    } else if (v.phase === "ready" && !v.online) {
      // a check opened while its own sleep step's doze runs: a press cannot wake it yet
      const doze = this._status?.readiness === "dozing";
      const left = this._dozeUntil == null ? 0 : Math.round((this._dozeUntil - Date.now()) / 1000);
      const wake = doze ? (left > 0 ? this._fmt(this._t.dozeHint, { n: left }) : this._fmt(this._t.dozeLate)) : t.text.wake;
      res = `<div class="res warn"><b>${wake}</b></div>`;
      btns = btn("skip", t.skip) + btn("close", t.close);
    } else if (v.phase === "ready" && v.external) {
      // the flat calibration measures nothing over time: lay the cap down and confirm
      btns = btn("done", t.done, "primary pulse") + btn("skip", t.skip) + btn("close", t.close);
    } else if (v.phase === "ready") {
      btns = btn("start", t.start, "primary pulse") + btn("skip", t.skip) + btn("close", t.close);
    } else if (v.phase === "running") {
      btns = (v.manual ? btn("done", t.done, "primary") : "") + btn("redo", t.redo) + btn("skip", t.skip);
    } else if (v.phase === "done") {
      const r = v.result || { status: "skip" };
      res = `<div class="res ${r.status}"><b>${t.status[r.status]}</b>${this._resultText(v.id, r)}</div>`;
      btns = btn("next", t.next, r.status === "fail" ? "" : "primary") + btn("redo", t.redo, r.status === "fail" ? "primary" : "");
    }
    const err = chk.err ? `<div class="res fail"><b>${chk.err}</b></div>` : "";
    return `<small class="of">${of}</small><h3>${t.steps[v.id]}</h3>${body}${live}${res}${err}<div class="btns">${btns}</div>`;
  }

  _resultText(id, r) {
    const t = this._t.check;
    const vals = { ...(r.values || {}) };
    if (vals.missing) vals.missing = vals.missing.split(",").map((k) => this._t.gestures[k] || k).join(", ");
    if (vals.via == null) vals.via = "—";
    if (typeof vals.expected === "number") vals.expected = Math.round(vals.expected);
    if (vals.extra) vals.extra = vals.extra.split(",").map((x) => { const [k, n] = x.split("×"); return `${this._t.gestures[k] || k} ×${n}`; }).join(", ");
    const parts = [];
    if (r.reason && t.reason[r.reason]) parts.push(this._fmt(t.reason[r.reason], vals));
    if (r.status !== "skip" || r.values) {
      if (id === "rest" && r.values) parts.push(this._fmt(t.values.rest, vals));
      if ((id === "turn_cw" || id === "turn_ccw") && r.values && r.reason !== "steps" && r.reason !== "knob_off") parts.push(this._fmt(t.values.turn, vals));
      if (id === "drift" && r.values && r.reason !== "drift") parts.push(this._fmt(t.values.drift, vals));
      if (id === "handle" && r.values) parts.push(this._fmt(t.values.handle, vals));
      if (id === "shake" && r.values && r.reason !== "shake_missed") parts.push(this._fmt(t.values.shake, vals));
      if (id === "sleep" && r.values?.doze_s != null && r.reason !== "long_doze") parts.push(this._fmt(t.values.sleep, vals));
    }
    return parts.join(" ");
  }

  // ------------------------------------------------------------------ hint model
  // A faint copy of the cap showing what to do, from the pose the step started in:
  // tilt the dot edge, a slow turn, turning over, a pick-up, leaning in the hand,
  // a press, a shake, a tap, a toss. Built-in model only.
  _setGhost(v) {
    const kind = v?.ghost?.type || null;
    if (!kind || !(this._chk?.ref || this._target)) {
      if (this._ghost) this._ghost.visible = false;
      this._ghostView = null;
      return;
    }
    this._ghostView = v;
    if (!this._ghost && this._cap && this._T) {
      const T = this._T;
      const g = this._cap.group.clone(true);
      g.traverse((o) => {
        if (!o.isMesh) return;
        o.material = (Array.isArray(o.material) ? o.material : [o.material]).map((m) => {
          const c = m.clone();
          c.transparent = true; c.opacity = 0.28; c.depthWrite = false;
          return c;
        });
        if (o.material.length === 1) o.material = o.material[0];
      });
      this._ghost = new T.Group();
      this._ghost.add(g);
      this._headingGroup.add(this._ghost);
    }
    if (this._ghost) this._ghost.visible = true;
    this._needsFrame = true;
    this._startRender();
  }

  _ghostPose(T) {
    const v = this._ghostView;
    const running = v?.phase === "running";
    // before Start the hint moves from the live pose
    const ref = (running && this._chk?.ref) || this._target;
    if (!v || !ref) return null;
    const q0 = new T.Quaternion(ref[1], ref[2], ref[3], ref[0]);
    const d = new T.Vector3(0, -1, 0).applyQuaternion(q0); // the dot edge in the world
    const h = new T.Vector3(d.x, d.y, 0);
    if (h.lengthSq() < 1e-6) h.set(0, -1, 0);
    h.normalize();
    const up = new T.Vector3(0, 0, 1);
    const sec = running ? this._chk.run?._elapsed?.() ?? v.elapsed ?? 0 : performance.now() / 1000; // live, not the 4 Hz panel tick
    let r;
    if (v.ghost.type === "tilt") {
      r = new T.Quaternion().setFromAxisAngle(new T.Vector3().crossVectors(h, up).normalize(), GHOST_TILT);
    } else if (v.ghost.type === "quarter") {
      // a quarter turn in 2 s, a 1 s rest, again: the pace of a turning wrist
      const p = Math.min(1, (sec % 3) / 2);
      r = new T.Quaternion().setFromAxisAngle(up, v.ghost.dir * (Math.PI / 2) * (1 - Math.cos(Math.PI * p)) / 2);
    } else if (v.ghost.type === "flip") {
      const p = Math.min(1, (sec % 3) / 1.5);
      r = new T.Quaternion().setFromAxisAngle(h, Math.PI * p);
    } else {
      const m = ghostMotion(v.ghost.type, sec);
      if (!m) return null;
      // tilts lift the dot edge (about the sideways axis); leans roll the cap
      // about its own dot axis, sensor y, which is what the tilt gesture reads
      const side = new T.Vector3().crossVectors(h, up).normalize();
      const lr = new T.Vector3(0, 1, 0).applyQuaternion(q0);
      r = new T.Quaternion().setFromAxisAngle(side, m.tilt || 0)
        .multiply(new T.Quaternion().setFromAxisAngle(lr, m.lean || 0));
      this._ghost.position.z = m.lift || 0;
      return r.multiply(q0);
    }
    this._ghost.position.z = 0;
    return r.multiply(q0);
  }

  // ------------------------------------------------------------------ 3D
  // Give the WebGL context back: dispose() alone keeps it, and the browser drops
  // the oldest one past about 16 (the editor preview makes a card per keystroke).
  // The canvas is swapped for a fresh one, as a lost context cannot be reused.
  _teardownScene() {
    if (this._raf) cancelAnimationFrame(this._raf);
    this._raf = null;
    this._ro?.disconnect();
    this._ro = null;
    const r = this._renderer;
    if (r) {
      r.dispose();
      r.forceContextLoss();
      const gl = this._el?.gl;
      if (gl?.isConnected) { const fresh = gl.cloneNode(false); gl.replaceWith(fresh); this._el.gl = fresh; }
    }
    this._renderer = this._scene = this._camera = this._pivot = this._headingGroup = null;
    this._cap = this._ghost = null;
  }

  async _ensureScene() {
    if (this._scene || this._sceneLoading) return;
    this._sceneLoading = true;
    let renderer, again = false;
    try {
      const T = await loadThree();
      this._T = T;
      const canvas = this._el.gl;
      renderer = new T.WebGLRenderer({ canvas, antialias: true, alpha: true });
      renderer.outputColorSpace = T.SRGBColorSpace;
      renderer.toneMapping = T.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.0;
      const scene = new T.Scene();
      const pmrem = new T.PMREMGenerator(renderer);
      scene.environment = pmrem.fromScene(new T.RoomEnvironment(), 0.04).texture;
      scene.add(new T.HemisphereLight(0xffffff, 0x404040, 0.8));
      const key = new T.DirectionalLight(0xffffff, 1.6);
      key.position.set(2, 4, 3);
      scene.add(key);
      const camera = new T.PerspectiveCamera(32, 1, 0.1, 50);
      // at table height: a cap lying level shows only its rim
      camera.position.set(0, 0, 6.2); // the cap takes about half the view's height
      camera.lookAt(0, 0, 0);
      this._camHome = camera.position.clone();
      // the check looks down at 35 degrees: a turn on the table is invisible edge-on
      this._camCheck = new T.Vector3(0, 6.2 * Math.sin(0.61), 6.2 * Math.cos(0.61));
      const world = new T.Group(); // z-up world -> three.js Y-up
      world.rotation.x = -Math.PI / 2;
      const heading = new T.Group();
      heading.rotation.z = Math.PI;
      const pivot = new T.Group(); // takes the sensor quaternion
      world.add(heading);
      heading.add(pivot);
      scene.add(world);
      if (this._config.model === "glb") {
        const gltf = await loadModel(T);
        const model = gltf.scene.clone(true);
        const box = new T.Box3().setFromObject(model);
        const size = box.getSize(new T.Vector3()).length();
        model.position.sub(box.getCenter(new T.Vector3()));
        const holder = new T.Group();
        holder.scale.setScalar(2.9 / size);
        holder.add(model);
        // the GLB is Y-up with its art's top towards -Z: model X, Y, Z are sensor -x, z, y
        holder.quaternion.setFromRotationMatrix(new T.Matrix4().makeBasis(
          new T.Vector3(-1, 0, 0), new T.Vector3(0, 0, 1), new T.Vector3(0, 1, 0)));
        pivot.add(holder);
      } else {
        const { buildCap } = await loadCap();
        this._cap = await buildCap(T, { metal: asset("tex_metal.webp"), resin: asset("tex_resin.webp") });
        this._cap.group.scale.setScalar(0.078); // millimetres -> scene units
        pivot.add(this._cap.group);
        this._capState = null;
        this._capLogo = undefined;
        if (this._status) this._setModelState(this._status.led, this._status.button);
      }
      if (canvas !== this._el?.gl || !this.isConnected) { // rebuilt or removed while loading
        renderer.dispose();
        renderer.forceContextLoss();
        again = true; // the new canvas asked for a scene while this one loaded
        return;
      }
      Object.assign(this, { _renderer: renderer, _scene: scene, _camera: camera, _pivot: pivot, _headingGroup: heading });
      this._q = new T.Quaternion();
      this._qTarget = new T.Quaternion();
      this._ro = new ResizeObserver(() => this._resize());
      this._ro.observe(this._el.stage);
      this._resize();
    } catch (err) {
      console.warn("triki-card: 3D view unavailable", err);
    } finally {
      this._sceneLoading = false;
      if (again && this._visible && this.isConnected) this._startRender();
    }
  }

  _resize() {
    if (!this._renderer) return;
    const r = this._el.stage.getBoundingClientRect();
    if (!r.width || !r.height) return;
    this._renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this._renderer.setSize(r.width, r.height, false);
    this._camera.aspect = r.width / r.height;
    this._camera.updateProjectionMatrix();
    this._needsFrame = true;
    this._startRender();
  }

  async _startRender() {
    if (this._raf || !this._visible) return;
    await this._ensureScene();
    if (!this._scene || this._raf || !this._visible) return;
    const tick = () => {
      this._raf = null;
      if (!this._visible || !this.isConnected) return;
      let moving = false;
      if (this._target) {
        this._qTarget.set(this._target[1], this._target[2], this._target[3], this._target[0]);
        if (this._q.angleTo(this._qTarget) > 0.0005) {
          this._q.slerp(this._qTarget, 0.35);
          moving = true;
        }
      } else if (this._q.angleTo(this._qTarget.identity()) > 0.0005) {
        this._q.slerp(this._qTarget, 0.1); // back to the rest pose while asleep
        moving = true;
      }
      const cam = this._chk ? this._camCheck : this._camHome;
      if (cam && this._camera.position.distanceTo(cam) > 0.01) {
        this._camera.position.lerp(cam, 0.15);
        this._camera.lookAt(0, 0, 0);
        moving = true;
      }
      const ghost = this._ghost?.visible ? this._ghostPose(this._T) : null;
      if (ghost) { this._ghost.quaternion.copy(ghost); moving = true; }
      if (moving || this._needsFrame) {
        this._pivot.quaternion.copy(this._q);
        this._renderer.render(this._scene, this._camera);
        this._needsFrame = false;
      }
      if (this._historyDirty) { this._drawHistory(); this._historyDirty = false; }
      if (moving || this._target) this._raf = requestAnimationFrame(tick);
    };
    this._needsFrame = true;
    this._raf = requestAnimationFrame(tick);
  }

  _drawHistory() {
    const cv = this._el.hist;
    if (!cv) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = cv.clientWidth, h = cv.clientHeight;
    if (!w || !h) return;
    if (cv.width !== w * dpr) { cv.width = w * dpr; cv.height = h * dpr; }
    const ctx = cv.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    ctx.strokeStyle = getComputedStyle(this).getPropertyValue("--divider-color") || "#444";
    ctx.beginPath(); ctx.moveTo(0, h / 2); ctx.lineTo(w, h / 2); ctx.stroke();
    const hist = this._history;
    if (hist.length < 2) return;
    const now = hist[hist.length - 1][0];
    let peak = 90;
    for (const p of hist) for (let i = 1; i < 4; i++) peak = Math.max(peak, Math.abs(p[i]));
    for (let axis = 1; axis < 4; axis++) {
      ctx.strokeStyle = AXIS_COLORS[axis - 1];
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      hist.forEach((p, k) => {
        const x = w - ((now - p[0]) / HISTORY_S) * w;
        const y = h / 2 - (p[axis] / peak) * (h / 2 - 2);
        if (k) ctx.lineTo(x, y); else ctx.moveTo(x, y);
      });
      ctx.stroke();
    }
  }
}

class TrikiCardEditor extends HTMLElement {
  setConfig(config) { this._config = config; this._render(); }
  set hass(hass) { this._hass = hass; this._render(); }
  _render() {
    if (!this._hass || !this._config) return;
    const T = cardStrings(this._hass);
    const e = T.editor;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.addEventListener("value-changed", (ev) => {
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: ev.detail.value } }));
      });
      this.appendChild(this._form);
    }
    this._form.computeLabel = (sc) => (sc.name === "device_id" ? "Triki" : e[sc.name] || sc.name);
    this._form.computeHelper = (sc) => (sc.name === "buttons" ? e.admin : undefined);
    this._form.hass = this._hass;
    // the card's defaults filled in: an unset list means all of it, and the
    // form must show it ticked, or ticking one item hides the rest
    const { show_controls, show_status, ...data } = cardConfig(this._config);
    this._form.data = data;
    // top to bottom as on the card
    const opts = (ids, label) => ids.map((value) => ({ value, label: label(value) }));
    this._form.schema = [
      { name: "device_id", selector: { device: { integration: "triki" } } },
      { name: "title", selector: { text: {} } },
      { name: "chips", selector: { select: { multiple: true, mode: "list", options: opts(CHIPS, (v) => e.opt[v]) } } },
      { name: "show_model", selector: { boolean: {} } },
      { name: "model", selector: { select: { mode: "dropdown", options: opts(["cap", "glb"], (v) => e.opt[v]) } } },
      { name: "show_values", selector: { boolean: {} } },
      { name: "show_history", selector: { boolean: {} } },
      { name: "show_gestures", selector: { boolean: {} } },
      { name: "buttons", selector: { select: { multiple: true, mode: "list", options: opts(BUTTONS,
        (v) => ({ calibrate: T.calibrate, align: T.reset, led: T.led, check: T.check.open })[v]) } } },
      { name: "show_help", selector: { boolean: {} } },
    ];
  }
}

if (!customElements.get("triki-card")) {
  customElements.define("triki-card", TrikiCard);
  customElements.define("triki-card-editor", TrikiCardEditor);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "triki-card",
    name: "Triki live 3D",
    description: "A Żabka Triki token in 3D, moving with the real one, with its gyro and accelerometer.",
    preview: false,
    documentationURL: "https://github.com/elenium3/ha-triki/blob/main/docs/live-card.md",
  });
}
