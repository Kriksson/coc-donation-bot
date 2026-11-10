/** Russian labels for server-provided calibration metadata. API keys stay unchanged. */
const stepLabels:Record<string,string>={
  home:'Домашняя деревня',clan_chat:'Клановый чат',donation_request:'Запрос на пожертвование',
  donation_panel:'Панель пожертвования',slot_colors:'Цвета ячеек',grid:'Разметка сетки',
  farm:'Фарм и обычная атака',optional:'Дополнительные элементы интерфейса',
};
const partLabels:Record<string,string>={
  frame_width:'Размер экрана',home:'Ориентир домашней деревни',open_chat:'Открыть чат (значок чата)',
  chat_panel:'Область панели чата',chat_requests:'Область запросов на пожертвование',clan_chat:'Ориентир кланового чата',
  close_chat:'Закрыть вкладку чата',chat_request_jump:'Значок перехода к запросу',chat_scroll_down:'Значок прокрутки вниз',
  donate_button:'Кнопка пожертвования',donation_panel:'Заголовок ресурсов для пожертвования',
  donation_elixir_button:'Кнопка эликсира',donation_elixir_selected:'Индикатор выбранного эликсира',
  donation_troop_bar:'Панель войск и осадных машин',donation_spell_bar:'Панель заклинаний',tap_outside_donation:'Нажатие вне панели для закрытия',
  donatable_troop:'Цвет доступного войска',disabled_troop:'Цвет недоступного войска',donatable_spell:'Цвет доступного заклинания',
  disabled_spell:'Цвет недоступного заклинания',troop_bar:'Сетка войск и осадных машин',spell_bar:'Сетка заклинаний',
  attack_button:'Кнопка атаки',unranked_battle:'Поиск обычного противника',find_match:'Вторая кнопка поиска (старый интерфейс)',
  return_home:'Вернуться домой',deploy_sequence:'Последовательность высадки войск',chat_groups:'Заголовок группового чата',
  clan_chat_tab:'Вкладка кланового чата (мечи)',loading:'Экран загрузки',popup_dismiss:'Закрытие всплывающего окна',popup:'Ориентир всплывающего окна',
};
const instructions:Record<string,string>={
  frame_width:'Откройте Clash of Clans и перейдите в домашнюю деревню с закрытым чатом. Нажмите «Сделать снимок», проверьте изображение и сохраните. Размер экрана определяется автоматически — область выделять не нужно.',
  home:'Оставайтесь в домашней деревне с закрытым чатом. При необходимости обведите уникальный элемент деревни, затем сохраните.',
  open_chat:'В домашней деревне с закрытым чатом найдите значок, открывающий чат. Сделайте снимок, обведите значок и сохраните. Можно вместо этого выбрать режим точки и нажать в центр значка.',
  chat_panel:'Откройте клановый чат, не открывая панель пожертвований. Сделайте снимок и обведите всю панель с сообщениями.',
  chat_requests:'Откройте клановый чат. Обведите область, где появляются запросы на пожертвование, обычно это область сообщений.',
  clan_chat:'Откройте клановый чат. Обведите элемент интерфейса, который виден в чате и скрывается панелью пожертвования, например заголовок чата.',
  close_chat:'Откройте клановый чат. Найдите оранжевую вкладку «<» справа, которая закрывает чат. Обведите её или нажмите в центр.',
  chat_request_jump:'Откройте клановый чат и найдите вверху или внизу значок перехода к запросу, появляющийся, когда запрос находится за пределами экрана. Обведите значок.',
  chat_scroll_down:'Откройте клановый чат. Если значок перехода к запросу уже настроен, этот шаг можно пропустить. Иначе прокрутите вниз и обведите нижний значок перехода.',
  donate_button:'Откройте клановый чат и найдите зелёную кнопку пожертвования в сообщении. Обведите её. Не выбирайте зелёную кнопку обмена: она выглядит похоже.',
  donation_panel:'Откройте клановый чат, нажмите кнопку пожертвования в запросе и оставьте белую панель открытой. При желании обведите заголовок «Ресурс пожертвования».',
  donation_elixir_button:'Оставьте панель пожертвования открытой. Слева от переключателя самоцветов выберите кнопку эликсира и нажмите в её центр. Бот проверяет, что выбран эликсир, а не самоцветы.',
  donation_elixir_selected:'Откройте панель пожертвования, выберите левую кнопку эликсира и обведите её целиком вместе с рамкой и фоном. Не захватывайте кнопку самоцветов.',
  donation_troop_bar:'Оставьте панель пожертвования открытой и обведите всю строку значков войск и осадных машин.',
  donation_spell_bar:'Оставьте панель пожертвования открытой и обведите всю панель заклинаний.',
  tap_outside_donation:'Оставьте панель пожертвования открытой. Нажмите на безопасное пустое место за её пределами, на затемнённом фоне.',
  donatable_troop:'Откройте панель пожертвования и найдите цветную ячейку войска или осадной машины, доступную для пожертвования. Обведите её центр.',
  disabled_troop:'Откройте панель пожертвования и обведите центр серой ячейки войска или осадной машины, недоступной для пожертвования.',
  donatable_spell:'Откройте панель пожертвования и обведите центр цветной ячейки заклинания, доступной для пожертвования.',
  disabled_spell:'Откройте панель пожертвования и обведите центр серой ячейки заклинания, недоступной для пожертвования.',
  troop_bar:'Откройте панель пожертвования. Обведите все видимые ячейки войск и осадных машин: от верхнего левого до нижнего правого угла. Затем укажите число столбцов и строк.',
  spell_bar:'Откройте панель пожертвования. Обведите все видимые ячейки заклинаний от верхнего левого до нижнего правого угла. Затем укажите число столбцов и строк.',
  attack_button:'Перейдите в домашнюю деревню, закройте чат и найдите кнопку «Атака» в левом нижнем углу. На старых версиях она может называться Attack!. Обведите её или нажмите в центр.',
  unranked_battle:'Откройте меню сетевой игры. Выберите «Найти противника» на левой карточке обычной битвы. Не выбирайте рейтинговую битву.',
  find_match:'Этот шаг нужен только для старых версий игры со вторым экраном поиска противника. На текущем интерфейсе его можно пропустить.',
  return_home:'После боя найдите кнопку «Домой» или «ОК» на экране результатов. Обведите её или нажмите в центр.',
  deploy_sequence:'Во время обычной атаки нажимайте сначала на значки армии, затем на места высадки в нужном порядке. Нумерованные круги показывают порядок нажатий и разброс. Можно отменить последнее нажатие и настроить разброс перед сохранением.',
  chat_groups:'При необходимости откройте группы чата (значок глобуса) и обведите заголовок или зелёную кнопку «+ Новая».',
  clan_chat_tab:'Пока открыты группы чата, обведите или нажмите вкладку с мечами и щитом, которая возвращает в клановый чат.',
  loading:'Необязательно: покажите экран загрузки Clash и обведите уникальный элемент.',
  popup_dismiss:'Необязательно: покажите всплывающее окно и обведите кнопку закрытия или подтверждения.',
  popup:'Необязательно: покажите всплывающее окно и обведите уникальный элемент.',
};
export const setupStepLabel=(id:string,label:string)=>stepLabels[id]||label;
export const setupPartLabel=(key:string,label:string)=>partLabels[key]||label;
export const setupInstruction=(key:string,instruction:string)=>instructions[key]||instruction;

const messages:Record<string,string>={
  'Builder resource readings or repeated attacks need another check':'Атаки отложены: нужно повторно проверить ресурсы или результат предыдущих атак деревни строителя',
  'Builder attacks produced no verified resource gain':'Атаки деревни строителя отложены: в трёх боях не удалось подтвердить прирост ресурсов',
  'Builder army is unsupported':'Состав армии деревни строителя пока не поддерживается',
  'Post-battle Builder resources are unreadable':'После боя не удалось прочитать ресурсы деревни строителя',
  'Builder farming paused':'Атаки деревни строителя временно приостановлены',

  'Preparing Android':'Подготовка Android', 'Starting Waydroid':'Запуск Waydroid',
  'Connecting to Android':'Подключение к Android', 'Waiting for Android to finish starting':'Ожидание запуска Android',
  'Import the Clash APK archive to finish installation':'Импортируйте архив APK Clash of Clans, чтобы завершить установку',
  'Installing Clash of Clans':'Установка Clash of Clans', 'Opening Clash of Clans':'Запуск Clash of Clans',
  'Ready — open Live view to sign in or prepare the game':'Готово — откройте трансляцию, чтобы войти в игру или подготовить её',
  'Runtime startup is already in progress':'Запуск среды уже выполняется',
  'Runtime preparation canceled. Use Retry when ready.':'Подготовка среды отменена. Нажмите «Повторить», когда будете готовы.',
  'Import between 1 and 32 APK files, up to 2 GB in total':'Импортируйте от 1 до 32 файлов APK общим размером до 2 ГБ',
  'The archive must contain only Clash of Clans APK files':'Архив должен содержать только APK-файлы Clash of Clans',
  'Choose a ZIP archive containing Clash APK files':'Выберите ZIP-архив с APK-файлами Clash',
  'APK archive is empty or too large':'Архив APK пуст или слишком велик',
  'ZIP must contain only unencrypted .apk files':'ZIP-архив должен содержать только незашифрованные файлы .apk',
  'Android has not finished starting (package service unavailable). Use Retry.':'Android ещё запускается (служба пакетов недоступна). Нажмите «Повторить».',
  'Clash did not stay running. Check APK/device compatibility.':'Clash закрылся после запуска. Проверьте совместимость APK и устройства.',
  'APK source could not be reached':'Не удалось подключиться к источнику APK',
  'APK source refused the update check':'Источник APK отклонил проверку обновлений',
  'APK download failed; existing Clash was not changed':'Не удалось скачать APK; установленная версия Clash не изменена',
  'APK download exceeds 2 GB':'Размер загружаемого APK превышает 2 ГБ', 'APK download was incomplete':'APK загрузился не полностью',
  'APK signature verification failed':'Не удалось проверить подпись APK',
  'Cannot encode screenshot':'Не удалось обработать снимок экрана', 'Cannot save template':'Не удалось сохранить шаблон',
  'Import a trusted Clash installation before using automatic updates':'Перед автоматическим обновлением импортируйте проверенную установку Clash',
  'Update signer does not match installed Clash; update rejected':'Подпись обновления не совпадает с установленной версией Clash; обновление отклонено',
  'Android did not confirm the Clash update':'Android не подтвердил обновление Clash',
  'Installed Clash version could not be confirmed':'Не удалось подтвердить установленную версию Clash',
  'No supported donation panel found. Open a donation panel, or draw the area manually.':'Панель пожертвования не распознана. Откройте её или выделите область вручную.',
  'Suggested area — check the outline before saving. Resource selection and slot colors still need manual verification.':'Предложенная область — проверьте контур перед сохранением. Выбор ресурса и цвета ячеек нужно проверить вручную.',
  'Saved resource readings are unreadable; farming needs a fresh check':'Не удалось прочитать сохранённые показатели ресурсов; перед фармом нужна новая проверка',
  'Account data is unreadable; restore its backup before continuing':'Не удалось прочитать данные аккаунтов; восстановите резервную копию, прежде чем продолжить',
  'A verified Clash player tag is required':'Нужен подтверждённый тег игрока Clash', 'Choose listed account roles':'Выберите задачи аккаунта из списка',
  'Unsupported account registry':'Формат реестра аккаунтов не поддерживается', 'Invalid account registry entry':'Некорректная запись реестра аккаунтов',
  'Active account is missing':'Активный аккаунт не найден', 'Unknown account profile':'Профиль аккаунта не найден',
  'Finish account setup or verify the current account before starting automation':'Завершите настройку аккаунта или проверьте текущий аккаунт перед запуском автоматизации',
  'Selected account changed; reload this page before continuing':'Выбранный аккаунт изменился. Перезагрузите страницу, прежде чем продолжить',
  'An account operation is unfinished; verify the current account first':'Операция с аккаунтом не завершена. Сначала проверьте текущий аккаунт',
  'Invalid account operation':'Недопустимая операция с аккаунтом', 'Use a nickname of 1–60 characters':'Имя должно содержать от 1 до 60 символов',
  'This village is not saved yet. Choose its tasks and press Save and verify account in Accounts.':'Эта деревня ещё не сохранена. Выберите задачи и нажмите «Сохранить и проверить аккаунт» в разделе «Аккаунты».',
  'A different account loaded; automation remains paused':'Загружен другой аккаунт; автоматизация остаётся приостановленной',
  'Choose a valid account scheduling mode':'Выберите допустимый режим расписания аккаунтов',
  'Choose a whole attack target from zero to six per hour':'Укажите целое число целей атаки от 0 до 6 в час',
  'Attack pacing and early finish require task-driven rotation':'Темп атак и досрочное завершение требуют ротации по задачам',
  'Choose a saved account with the Donating role as the main account':'Выберите сохранённый аккаунт с задачей «Пожертвования» в качестве основного',
  'Account visit times must be whole seconds':'Время посещения аккаунта должно быть указано целым числом секунд',
  'Account check interval must be between five minutes and one day':'Интервал проверки аккаунтов должен быть от 5 минут до 1 дня',
  'Finish adding or verifying the loaded account first':'Сначала завершите добавление аккаунта или проверку загруженного аккаунта',
  'Account rotation is disabled':'Ротация аккаунтов выключена', 'Main donating account is unavailable':'Основной аккаунт для пожертвований недоступен',
  'No saved account is selected':'Сохранённый аккаунт не выбран', 'Account has an unresolved action; automatic switching paused':'Для аккаунта не завершено действие; автоматическое переключение приостановлено',
  'Screenshot expired. Capture again.':'Срок действия снимка истёк. Сделайте снимок ещё раз.',
  'Unknown calibration part':'Неизвестная часть калибровки', 'Screen size changed. Calibrate screen size first.':'Размер экрана изменился. Сначала откалибруйте размер экрана.',
  'Invalid resource status':'Некорректный статус ресурсов',
  'Select a point':'Укажите точку', 'Selection is outside the screenshot':'Выделенная область находится за пределами снимка',
  'Choose between 1 and 500 taps':'Укажите от 1 до 500 нажатий', 'Farm deploy jitter must be between 0 and 40':'Разброс высадки при фарме должен быть от 0 до 40',
  'Draw a box':'Выделите прямоугольную область', 'Box must fit inside the screenshot':'Область должна целиком помещаться на снимке',
  'Calibrate the donation bar area first.':'Сначала откалибруйте область панели пожертвований.', 'Invalid grid rows or columns':'Некорректное число строк или столбцов сетки',
  'Bot is stopping. Try again when it has stopped.':'Бот останавливается. Повторите попытку после остановки.',
  'Settings update canceled by Stop. Changes were not applied.':'Обновление настроек отменено командой остановки. Изменения не применены.',
  'Settings update canceled. The bot will not restart.':'Обновление настроек отменено. Бот не будет перезапущен.',
  'Settings saved — bot restarting':'Настройки сохранены — перезапуск бота', 'Settings saved, but the bot could not restart.':'Настройки сохранены, но перезапустить бота не удалось.',
  'Wait for the settings update to finish':'Дождитесь завершения обновления настроек', 'Unknown diagnostic action':'Неизвестное диагностическое действие',
  'Resource targets must satisfy 1 ≤ start below < refill to ≤ 100':'Порог начала фарма должен быть ниже целевого уровня пополнения (от 1 до 100%)',
  'Unlocked resources could not be verified':'Не удалось проверить доступные ресурсы',
  'Resources are above the refill threshold':'Ресурсы выше порога начала пополнения',
  'Resource targets reached':'Целевой уровень ресурсов достигнут',
  'Request failed':'Запрос не выполнен',
  'Farm interval must be between 60 and 86400 seconds':'Интервал фарма должен быть от 60 до 86 400 секунд',
  'Resource check stopped':'Проверка ресурсов остановлена',
  'Home controls lost during resource check':'Во время проверки ресурсов потеряно управление домашней деревней',
  'Waydroid session could not stop. Run the server as the desktop session user.':'Не удалось остановить сеанс Waydroid. Запустите сервер от имени пользователя графического сеанса.',
  'Account backup checksum failed':'Контрольная сумма резервной копии аккаунтов не совпала',
  'Account backup refuses symbolic links':'Резервная копия аккаунтов не может содержать символические ссылки',
  'Invalid original account marker':'Некорректная отметка исходного аккаунта', 'Duplicate account registry entry':'Повторяющаяся запись реестра аккаунтов',
  'Account registry must retain one original profile and an active account':'В реестре должен оставаться исходный профиль и активный аккаунт',
  'Invalid account profile':'Некорректный профиль аккаунта', 'Account profile is outside its installation':'Профиль аккаунта находится вне папки установки',
  'Finish or cancel the native layout edit before starting automation or switching accounts':'Завершите или отмените изменение игрового макета перед запуском автоматизации или сменой аккаунта',
  'Unexpected account loaded during a switch':'Во время переключения загрузился неожиданный аккаунт',
  'Unknown account action':'Неизвестное действие с аккаунтом', 'Save your current account first':'Сначала сохраните текущий аккаунт', 'Unknown saved account':'Сохранённый аккаунт не найден',
  'Account selection changed during startup; retry after verification':'Выбор аккаунта изменился во время запуска. Повторите попытку после проверки',
  'Loaded village is not saved. Add it in Accounts before starting automation.':'Загруженная деревня не сохранена. Добавьте её в разделе «Аккаунты» перед запуском автоматизации.',
  'Choose tasks for the loaded saved account before starting automation':'Перед запуском автоматизации выберите задачи для загруженного аккаунта',
  'Account startup stopped before selecting the verified profile':'Запуск аккаунта остановлен до выбора проверенного профиля',
  'Saved accounts must use the same Android device before automatic startup':'Для автоматического запуска все сохранённые аккаунты должны использовать одно устройство Android',
  'Loaded account has an unresolved action; verify and recover it first':'Для загруженного аккаунта не завершено действие. Сначала проверьте и восстановите его',
  'Wait for account recognition to finish':'Дождитесь распознавания аккаунта',
  'Failed to open clan chat — check calibration / that CoC is visible.':'Не удалось открыть клановый чат. Проверьте калибровку и убедитесь, что Clash of Clans виден.',
  'Could not reach home':'Не удалось вернуться в деревню', 'Could not open Attack menu':'Не удалось открыть меню атаки',
  'Could not confirm an unranked opponent':'Не удалось подтвердить выбор обычного противника',
  'Save an attack plan before selecting the new engine':'Сохраните план атаки перед выбором нового алгоритма',
  'Review the army on this device before using its plan':'Проверьте состав армии на этом устройстве перед использованием плана',
  'Complete a supervised attack with this saved routine before scheduling it':'Сначала выполните атаку под наблюдением с этой сохранённой схемой, затем добавляйте её в расписание',
  'Attack plan is damaged; review and save it again':'План атаки повреждён. Проверьте его и сохраните заново',
  'Open home, use Prepare opponent, then map it so your camera can be restored':'Откройте деревню, нажмите «Подготовить противника» и составьте карту, чтобы можно было вернуть камеру',
  'Observation belongs to a different device; inspect this device again':'Наблюдение относится к другому устройству. Проведите осмотр на этом устройстве ещё раз',
  'Observation changed; reload before saving the plan':'Данные наблюдения изменились. Перезагрузите их перед сохранением плана',
  'Map an opponent before creating an attack preview':'Сначала составьте карту противника, затем создавайте предварительный просмотр атаки',
  'Mark corners within the surveyed image':'Отметьте углы внутри исследованного изображения',
  'Repeated army identity; review the duplicate cards before planning':'В армии обнаружены одинаковые отряды. Проверьте повторяющиеся карточки перед планированием',
  'Check each used army card before saving the plan':'Перед сохранением плана проверьте каждую используемую карточку армии',
  'Army reference image is missing':'Не найдено эталонное изображение армии',
  'Recover the unfinished attack before executing another preview':'Завершите восстановление незаконченной атаки перед выполнением другого плана',
  'Preview and save the reviewed plan before running it':'Проверьте предварительный просмотр и сохраните план перед запуском',
  'This preview has already been used; inspect a new opponent':'Этот предварительный просмотр уже использован. Осмотрите нового противника',
  'Opponent preview expired; map the current opponent again':'Срок действия предварительного просмотра истёк. Составьте карту текущего противника ещё раз',
  'Map reference is missing':'Не найдена эталонная карта',
  'Interrupted attack recovered; prepare a new opponent when ready':'Прерванная атака восстановлена. Подготовьте нового противника, когда будете готовы',
  'Please check your input and try again':'Проверьте введённые данные и повторите попытку',
  'NetworkError when attempting to fetch resource.':'Не удалось связаться с сервером. Проверьте подключение и повторите попытку.',
  'Failed to fetch':'Не удалось связаться с сервером. Проверьте подключение и повторите попытку.',
  'Screenshot could not be captured':'Не удалось сделать снимок экрана',
};

export type PresentedMessage={text:string;original?:string};
export function presentMessage(value:unknown):PresentedMessage{
  const raw=String(value??'').trim();
  if(!raw)return {text:''};
  if(messages[raw])return {text:messages[raw]};
  let m:RegExpMatchArray|null;
  if((m=raw.match(/^Clash update check could not finish: (.+)$/)))return {text:'Не удалось проверить обновления Clash: '+m[1],original:raw};
  if((m=raw.match(/^Clash (.+) is up to date(?: \(no downgrade installed\))?$/)))return {text:`Clash версии ${m[1]} уже обновлён`};
  if((m=raw.match(/^Checking Clash updates on (.+)$/)))return {text:`Проверка обновлений Clash на ${m[1]}`};
  if((m=raw.match(/^Verifying Clash update signature$/)))return {text:'Проверка подписи обновления Clash'};
  if((m=raw.match(/^Installing Clash (.+)$/)))return {text:`Установка Clash ${m[1]}`};
  if((m=raw.match(/^Downloading Clash update — (.+)$/)))return {text:`Загрузка обновления Clash — ${m[1]}`};
  if((m=raw.match(/^Builder resources unreadable: (.+)$/)))return {text:'Атаки деревни строителя отложены. '+presentMessage(m[1]).text};
  if((m=raw.match(/^(.+) balance or capacity is unreadable$/)))return {text:`Не удалось прочитать баланс или вместимость: ${resourceName(m[1])}`};
  if((m=raw.match(/^(.+) must be a finite number$/)))return {text:`Для параметра «${m[1]}» укажите конечное число`};
  if((m=raw.match(/^(.+) must be one of: (.+)$/)))return {text:`Для параметра «${m[1]}» выберите одно из допустимых значений: ${m[2]}`,original:raw};
  if((m=raw.match(/^Choose a listed value for (.+)$/)))return {text:`Выберите допустимое значение для параметра «${m[1]}»`};
  if((m=raw.match(/^(.+) must be on or off$/)))return {text:`Для параметра «${m[1]}» укажите «включено» или «выключено»`};
  if((m=raw.match(/^(.+) must be a number$/)))return {text:`Для параметра «${m[1]}» укажите число`};
  if((m=raw.match(/^(.+) must be a finite, non-negative number$/)))return {text:`Для параметра «${m[1]}» укажите конечное неотрицательное число`};
  if((m=raw.match(/^(.+) must be between (.+) and (.+)$/)))return {text:`Значение параметра «${m[1]}» должно быть от ${m[2]} до ${m[3]}`};
  if((m=raw.match(/^(.+) must be a whole number$/)))return {text:`Для параметра «${m[1]}» укажите целое число`};
  if((m=raw.match(/^(.+) must be greater than zero$/)))return {text:`Значение параметра «${m[1]}» должно быть больше нуля`};
  if((m=raw.match(/^Refilling (.+)$/)))return {text:`Пополнение ресурсов: ${m[1].split(', ').map(resourceName).join(', ')}`};
  if((m=raw.match(/^This account does not have the (.+) role$/)))return {text:`У аккаунта нет задачи «${roleName(m[1])}»`};
  if((m=raw.match(/^Farm one-shot: stopped \((.+)\)$/)))return {text:`Разовая атака остановлена: ${presentMessage(m[1]).text}`,original:raw};
  if((m=raw.match(/^Farm one-shot: success=(true|false) \((.+)\)$/)))return {text:`Разовая атака ${m[1]==='true'?'завершена':'не выполнена'}: ${presentMessage(m[2]).text}`,original:raw};
  if((m=raw.match(/^(.+) is saved and verified\. No separate check is needed\. The bot stays stopped until you press Start\.$/)))return {text:`Аккаунт «${m[1]}» сохранён и проверен. Дополнительная проверка не нужна. Бот останется остановленным, пока вы не нажмёте «Запустить».`};
  if((m=raw.match(/^Sign in through Live view, return to the home village, and release control\. Then choose tasks and press Save and verify account\.$/)))return {text:'Войдите в аккаунт через трансляцию, вернитесь в домашнюю деревню и отпустите управление. Затем выберите задачи и нажмите «Сохранить и проверить аккаунт».'};
  if((m=raw.match(/^Could not open (.+) — (.+)$/)))return {text:`Не удалось открыть ${m[1]} — ${m[2]}`,original:raw};
  if((m=raw.match(/^Could not open (.+): (.+)$/)))return {text:`Не удалось открыть ${m[1]}: ${m[2]}`,original:raw};
  if((m=raw.match(/^Invalid (.+)$/)))return {text:`Некорректное значение: ${m[1]}`,original:raw};
  if((m=raw.match(/^Unknown (.+)$/)))return {text:`Неизвестное значение: ${m[1]}`,original:raw};
  // Keep Russian messages and technical identifiers intact. For an unrecognized
  // English sentence show a useful fallback while retaining the exact source.
  if(/[A-Za-z]{3}/.test(raw)&&!/[А-Яа-яЁё]/.test(raw))return {text:'Сообщение системы. Исходный текст сохранён в технических подробностях.',original:raw};
  return {text:raw};
}
function resourceName(value:string){return ({gold:'золото',elixir:'эликсир',dark_elixir:'тёмный эликсир'} as Record<string,string>)[value]||value;}
function roleName(value:string){return ({farming:'фарм',donating:'пожертвования',upgrading:'улучшения',builder_base:'строительная база'} as Record<string,string>)[value]||value;}
