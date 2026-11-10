"""Russian presentation of engine events; original diagnostics stay intact."""
import re

_NAMES={
    'Spell Factory':'Фабрика заклинаний','Dark Spell Factory':'Фабрика тёмных заклинаний',
    'Barracks':'Казарма','Dark Barracks':'Тёмная казарма','Laboratory':'Лаборатория',
    'Star Laboratory':'Звёздная лаборатория','Elixir Collector':'Сборщик эликсира',
    'Gold Mine':'Золотая шахта','Gold Storage':'Хранилище золота','Elixir Storage':'Хранилище эликсира',
    'Dark Elixir Storage':'Хранилище тёмного эликсира','Dark Elixir Drill':'Скважина тёмного эликсира',
    'Army Camp':'Военный лагерь','Town Hall':'Ратуша','Builder Hall':'Дом строителя',
    'Clan Castle':'Крепость клана','Blacksmith':'Кузница','Hero Hall':'Зал героев',
    'Barbarian King':'Король варваров','Archer Queen':'Королева лучниц',
    'Dragon':'Дракон','Baby Dragon':'Дракончик','Sneaky Archer':'Скрытая лучница',
    'Bowler':'Вышибала','Wall':'Стена','Cannon':'Пушка','Archer Tower':'Башня лучниц',
    'Battle Machine':'Боевая машина','Night Witch':'Ночная ведьма',
    'Mortar':'Мортира','Air Defense':'ПВО','Wizard Tower':'Башня магов',
}
_KINDS={'buildings':'зданий','research':'войск','pets':'питомцев'}
_RESOURCES={'gold':'золота','elixir':'эликсира','dark_elixir':'тёмного эликсира'}
_PHASES={
    'Starting':'Запускаю бота','At home':'В основной деревне',
    'Watching clan chat':'Слежу за запросами клана','Checking requests':'Проверяю запросы клана',
    'Opening donation':'Открываю окно пожертвования','Donating':'Передаю войска',
    'Opening attack':'Открываю меню атаки','Finding opponent':'Ищу противника',
    'In battle':'Идёт бой','Leaving battle':'Проверяю результат боя',
    'Returning home':'Возвращаюсь в деревню','Recovering':'Восстанавливаю состояние игры',
    'Arranging layout':'Проверяю расстановку','Checking upgrades':'Проверяю улучшения',
    'Visiting Builder Base':'Перехожу в деревню строителя',
    'On home village':'В основной деревне','On clan chat':'В чате клана',
    'Checking recommended upgrades':'Проверяю рекомендуемые улучшения',
    'Opening Attack menu':'Открываю меню атаки',
    'Searching for a farm match':'Ищу противника для фарма',
    'Farm battle in progress':'Идёт бой',
    'Returning home after farm':'Возвращаюсь домой после боя',
    'Recovering (reopening chat)':'Восстанавливаю состояние игры',
}


def activity_label(text):
    if not text:return None
    if text.startswith('Builder Base — '):
        phase=text.removeprefix('Builder Base — ').replace('_',' ')
        return {'travelling to builder base':'Перехожу в деревню строителя',
                'builder home':'В деревне строителя','collecting resources':'Собираю ресурсы деревни строителя',
                'collecting elixir cart':'Забираю эликсир из тележки','checking upgrades':'Проверяю улучшения в деревне строителя',
                'opening attack':'Открываю атаку в деревне строителя','matchmaking':'Ищу противника в деревне строителя',
                'battle':'Идёт бой в деревне строителя','leaving results':'Завершаю бой в деревне строителя',
                'returning to home village':'Возвращаюсь в основную деревню'}.get(phase,'Проверяю деревню строителя')
    if text in _PHASES:return _PHASES[text]
    for source,target in _PHASES.items():
        if text.startswith(source+' ('):return target
    if re.search('[А-Яа-яЁё]', text):return text[:500]
    if text.startswith('Switching to '):return 'Переключаюсь на '+text.removeprefix('Switching to ')
    return 'Выполняю действие в игре'


def error_label(text):
    if not text:return None
    value=str(text)
    rules=(
        ('SurfaceFlinger','Графическая система Android завершилась с ошибкой. Работа бота остановлена.'),
        ('Star Bonus acknowledgement','Не удалось подтвердить закрытие окна звёздного бонуса. Повторные нажатия остановлены.'),
        ('Edit Army control was not verified','Не распознана кнопка «Изменить армию».'),
        ('My Army did not open','Не удалось открыть окно армии.'),
        ('Army capacity changed','Не удалось подтвердить вместимость армии по двум снимкам.'),
        ('Army composition is uncertain','Не удалось подтвердить состав армии.'),
        ('Home navigation was not verified','Не удалось подтвердить возвращение в деревню.'),
        ('dark_elixir balance or capacity','Не удалось прочитать баланс или вместимость хранилища тёмного эликсира.'),
        ('gold balance or capacity','Не удалось прочитать баланс или вместимость хранилища золота.'),
        ('elixir balance or capacity','Не удалось прочитать баланс или вместимость хранилища эликсира.'),
        ('Screenshot time budget exhausted','Android не передал снимок экрана за отведённое время.'),
        ('Screencap failed','Не удалось получить снимок экрана Android.'),
        ('No route to host','Потеряно сетевое соединение с Android.'),
        ('unauthorized','Android ожидает разрешения на подключение ADB.'),
        ('not calibrated','Сначала завершите настройку распознавания.'),
        ('Stop requested','Действие остановлено по запросу пользователя.'),
    )
    for marker,label in rules:
        if marker in value:return label
    if re.search('[А-Яа-яЁё]',value):return value[:500]
    return 'Не удалось завершить действие. Подробности доступны в журнале.'


def present_event(level,text):
    text=str(text);technical=level=='DEBUG';category='system'
    summary=None
    if text.startswith('Activity: '):
        summary=activity_label(text.removeprefix('Activity: '))
    elif text.startswith('CoC Donation Bot starting'):
        summary='Запускаю бота и проверяю подключение к игре'
    elif text in ('Bot stopped','Bot stopped.'):
        summary='Бот остановлен'
    elif text.startswith('Farm attack requested'):
        summary='Атака добавлена в очередь';category='farm'
    elif text.startswith('Preparing farming army'):
        summary='Проверяю войска и вместимость военных лагерей';category='farm'
    elif text.startswith('Farm failed before deploy'):
        wait=re.search(r'cooldown (\d+)s',text)
        delay=int(wait[1]) if wait else 300
        summary='Атака не началась. '+error_label(text)+f' Повторная попытка через {max(1,delay//60)} мин.';category='farm'
    elif text.startswith('Pausing donations for resource refill attack'):
        summary='Готовлю основную деревню к атаке';category='farm'
    elif text.startswith('Automatic attack: reading army bar'):
        summary='Распознаю войска на панели боя';category='farm'
    elif text.startswith('Farming army ready:'):
        summary='Армия готова к атаке';category='farm'
    elif match:=re.match(r'Deployment confirmed: (.+) ×(\d+)',text):
        unit,count=match.groups();unit=_NAMES.get(unit.replace('_',' ').title(),unit.replace('_',' '))
        summary=f'Высажены войска: {unit} ×{count}';category='farm'
    elif text.startswith('Watching for battle results'):
        summary='Войска высажены. Ожидаю завершения боя';category='farm'
    elif text.startswith('Battle results confirmed'):
        summary='Результат боя подтверждён. Возвращаюсь в деревню';category='farm'
    elif text.startswith('Interrupted attack recovered'):
        summary='Возвращение после боя подтверждено';category='farm'
    elif text.startswith('Recorded farm completion'):
        summary='Атака учтена. Следующий запуск — по расписанию';category='farm'
    elif text.startswith('Farm attempt did not complete'):
        summary='Атака не завершена. Проверяю текущее состояние игры';category='farm'
    elif text.startswith('Running recovery sequence'):
        summary='Проверяю экран и восстанавливаю состояние игры';category='device'
    elif text.startswith('Recovery has not confirmed'):
        summary='Восстановление ещё не подтвердило нужный экран';category='device'
    elif text.startswith('ADB health check OK'):
        summary='Подключение к Android проверено';category='device'
    elif text.startswith('Force-stopping '):
        summary='Закрываю игру';category='device'
    elif text.startswith(('Starting Clash','Launching Clash')):
        summary='Открываю Clash of Clans';category='device'
    elif text.startswith('Upgrade confirmed running: '):
        item=text.split(': ',1)[1];summary='Улучшение запущено: '+_NAMES.get(item,item);category='upgrade'
    elif match:=re.match(r'Starting recommended (buildings|research|pets) upgrade: (.+) for (\d+) (gold|elixir|dark_elixir)',text):
        kind,item,amount,resource=match.groups();amount=f'{int(amount):,}'.replace(',',' ')
        summary=f'Запускаю улучшение: {_NAMES.get(item,item)} — {amount} {_RESOURCES[resource]}';category='upgrade'
    elif match:=re.match(r'Upgrade check \((buildings|research|pets)\): ([\w_]+)',text):
        kind,status=match.groups();category='upgrade'
        if status=='nothing_eligible':summary='Доступных улучшений '+_KINDS[kind]+' пока нет'
        elif status=='busy':summary='Улучшение '+_KINDS[kind]+' уже выполняется'
        elif status=='needs_review':summary='Для продолжения улучшений нужна проверка';
        else:summary='Проверка улучшений '+_KINDS[kind]+' завершена';technical=True
    elif text.startswith('Resource farming: '):
        summary='Проверяю запас ресурсов перед фармом';category='farm'
    elif text.startswith('Settings saved'):
        summary='Настройки сохранены'
    elif text.startswith('Settings update'):
        summary='Применяю настройки'
    elif text.startswith('Home ready'):
        summary='Основная деревня готова';category='farm';technical=True
    elif text.startswith('Button label OCR') and level in ('WARNING','ERROR','CRITICAL'):
        summary='Не удалось распознать подпись кнопки за отведённое время';technical=False
    elif text.startswith(('Task start:','Task timing:','Bot mode:','GameState','Saved ',
                          'Screencap OK','ADB:','ADB exec-out:','Trying Attack!',
                          'Trying 5 Attack!','Attack menu opened','Between attacks:',
                          'Button label OCR','Account handoff:','Farming army:')):
        summary='Техническая проверка';technical=True
    elif match:=re.match(r'Builder Base: deployment confirmed for (\w+) slot (\d+)',text):
        unit,slot=match.groups();name=_NAMES.get(unit.replace('_',' ').title(),unit.replace('_',' '))
        summary=f'Деревня строителя: высажен отряд «{name}», ячейка {int(slot)+1}';category='builder'
    elif text.startswith('Builder Base: second stage'):
        summary='Перехожу ко второй части боя в деревне строителя';category='builder'
    elif text.startswith('Builder Base attack skipped: army'):
        summary='Атака в деревне строителя отложена: состав армии не подтверждён';category='builder'
    elif match:=re.match(r'Builder Base collection confirmed: (gold|elixir) \+(\d+)',text):
        resource,amount=match.groups();summary=f'Деревня строителя: собрано {int(amount):,} {_RESOURCES[resource]}'.replace(',',' ');category='builder'
    elif text.startswith('Builder Base farming: '):
        summary='Проверяю необходимость пополнения ресурсов деревни строителя';category='builder'
    elif text.startswith('Builder Base visit completed:'):
        category='builder'
        if 'resource readings or repeated attacks' in text:
            summary='Атаки в деревне строителя отложены: не подтверждены ресурсы или результат предыдущих атак'
        else:summary='Проверка деревни строителя завершена'
    elif 'Builder' in text or 'builder' in text:
        category='builder'
        if level not in ('WARNING','ERROR','CRITICAL'):
            summary='Проверяю деревню строителя';technical=True
    if summary is None:
        if level in ('WARNING','ERROR','CRITICAL'):
            summary=error_label(text)
        elif re.search('[А-Яа-яЁё]',text):summary=text
        else:summary='Служебное событие';technical=True
    return {'summary':summary,'technical':technical,'category':category}
