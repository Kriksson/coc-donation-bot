"""GUI-editable settings definitions and persistence helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable

from coc_bot.config import BotConfig, load_config, load_user_settings, save_user_settings
from coc_bot.control.themes import normalize_theme_id, theme_label, theme_labels
from coc_bot.control.timing_presets import (
    PRESET_LABELS,
    RAW_TIMING_FIELD_KEYS,
    apply_timing_preset,
    infer_preset_from_timing,
    normalize_timing_preset,
    timing_preset_id_from_label,
    timing_preset_label,
)


@dataclass(frozen=True)
class SettingField:
    key: str
    label: str
    description: str
    kind: str  # int, float, bool, str, int_pair, choice
    getter: Callable[[BotConfig], Any]
    section: str
    yaml_path: tuple[str, ...]  # e.g. ("timing", "anti_idle_seconds")
    choices: tuple[str, ...] = ()  # for kind "choice"


def _pair(lo_hi: tuple[int, int]) -> str:
    return f"{lo_hi[0]}, {lo_hi[1]}"


# Shared by browser validation and desktop settings persistence.
UPGRADE_INTEGER_LIMITS = {
    'farm_resource_start_percent': (1, 99),
    'farm_resource_target_percent': (2, 100),
    'farm_interval_seconds': (60, 86400),
    'builder_base_interval_seconds': (300, 86400),
    'builder_base_builders_reserved': (0, 3),
    'builder_base_gold_reserve': (0, 20_000_000),
    'builder_base_elixir_reserve': (0, 20_000_000),
    'upgrade_interval_seconds': (60, 86400),
    'upgrade_builders_reserved': (0, 6),
    'upgrade_gold_reserve': (0, 100_000_000),
    'upgrade_elixir_reserve': (0, 100_000_000),
    'upgrade_dark_elixir_reserve': (0, 100_000_000),
}


SETTINGS: list[SettingField] = [
    SettingField('builder_base_collect_resources','Собирать ресурсы на Строительной базе','Собирать проверенные значки ресурсов у рудников и сборщиков в обеих деревнях, а также награды за оборону из тележки с эликсиром. Работает без атак и улучшений.','bool',lambda c:c.builder_base_collect_resources,'Builder Base',('builder_base','collect_resources')),
    SettingField('builder_base_progression_enabled','Развитие Строительной базы','Сначала улучшать Звёздную лабораторию, затем строить недостающие сооружения и улучшать существующие. Переход на следующий уровень Ратуши строителя требует полной проверки максимальных уровней построек.','bool',lambda c:c.builder_base_progression_enabled,'Builder Base',('builder_base','progression_enabled')),
    SettingField('builder_base_research_enabled','Исследования на Строительной базе','Тратить эликсир строителя на поддерживаемые войска для фарма. Ведьма ночи проверена; развитие также поддерживает Скрытого лучника 2–30 уровня, если уровень распознан. При незнакомом окне подтверждения бот безопасно остановится.','bool',lambda c:c.builder_base_research_enabled,'Builder Base',('builder_base','research_enabled')),
    SettingField('builder_base_elixir_reserve','Оставлять эликсир строителя','Минимальный остаток эликсира строителя после исследования.','int',lambda c:c.builder_base_elixir_reserve,'Builder Base',('builder_base','elixir_reserve')),
    SettingField('builder_base_attacks_enabled','Пополнять ресурсы Строительной базы','Использовать проценты ресурсов из раздела «Атаки», чтобы пополнять хранилища Строительной базы перед проверкой улучшений. Поддерживаются начальные лагеря варваров или шесть Ведьм ночи с Боевой машиной. При неизвестном составе войск или счётчиках фарм откладывается, проверки улучшений продолжаются.','bool',lambda c:c.builder_base_attacks_enabled,'Builder Base',('builder_base','attacks_enabled')),
    SettingField('builder_base_upgrades_enabled','Улучшать постройки Строительной базы','Тратить золото или эликсир строителя с учётом выбранного резерва и свободных строителей. Режим развития строит новые сооружения и выполняет отдельную проверку Ратуши строителя. Самоцветы и предметы не используются.','bool',lambda c:c.builder_base_upgrades_enabled,'Builder Base',('builder_base','upgrades_enabled')),
    SettingField('builder_base_builders_reserved','Оставлять свободными строителей базы','Влияет только на строителей Строительной базы.','int',lambda c:c.builder_base_builders_reserved,'Builder Base',('builder_base','builders_reserved')),
    SettingField('builder_base_gold_reserve','Оставлять золото строителя','Минимальный остаток золота строителя после улучшения.','int',lambda c:c.builder_base_gold_reserve,'Builder Base',('builder_base','gold_reserve')),
    SettingField('progression_enabled','Развитие деревни','Сначала улучшать лабораторию, затем строить недостающие сооружения, развивать деревню и готовить армии для фарма на основе проверенных открытий. Улучшение Ратуши требует полной проверки максимальных уровней построек.','bool',lambda c:c.progression_enabled,'Upgrades',('progression','enabled')),
    SettingField('progression_rearrange','Искать место для постройки','Перемещать предварительный просмотр новой постройки, чтобы найти подходящее место до оплаты. Удаление обычных препятствий настраивается отдельно.','bool',lambda c:c.progression_rearrange,'Upgrades',('progression','rearrange')),
    SettingField('layouts_enabled','Автоматические оборонительные расстановки','По умолчанию выключено. Если включить для этого аккаунта, бот очистит препятствия в зоне строительства и импортирует подходящую оборонительную расстановку. Активация выполняется только после завершения импорта и проверки домашней деревни.','bool',lambda c:c.layouts_enabled,'Upgrades',('layouts','enabled')),
    SettingField('layouts_replace_inactive','Заменять неактивные расстановки','Разрешить автоматической расстановке занимать свободную неактивную ячейку. Текущая активная деревня сохраняется, пока замена не будет завершена.','bool',lambda c:c.layouts_replace_inactive,'Upgrades',('layouts','replace_inactive')),
    SettingField('progression_clear_obstacles','Убирать обычные препятствия','Разрешить удалять обычные препятствия за проверенное количество золота или эликсира, чтобы освободить место для построек. Для сезонных препятствий есть отдельная настройка.','bool',lambda c:c.progression_clear_obstacles,'Upgrades',('progression','clear_obstacles')),
    SettingField('progression_clear_seasonal_obstacles','Убирать сезонные препятствия','Также разрешить навсегда убирать сезонные препятствия за проверенное количество золота или эликсира. Самоцветы, лопаты и действия с хранилищами не используются.','bool',lambda c:c.progression_clear_seasonal_obstacles,'Upgrades',('progression','clear_seasonal_obstacles')),
    SettingField('upgrade_buildings_enabled','Автоматически улучшать постройки','Использовать свободных строителей. Развитие деревни добавляет строительство и полные проверки построек; иначе используются рекомендованные улучшения.','bool',lambda c:c.upgrade_buildings_enabled,'Upgrades',('upgrades','buildings_enabled')),
    SettingField('upgrade_research_enabled','Автоматически исследовать войска','Начинать первое подходящее рекомендованное исследование войска или заклинания, когда лаборатория свободна. Самоцветы и предметы не используются.','bool',lambda c:c.upgrade_research_enabled,'Upgrades',('upgrades','research_enabled')),
    SettingField('upgrade_pets_enabled','Автоматически улучшать питомцев','Улучшать подходящего незанятого питомца, когда ячейка улучшения свободна. Используется тёмный эликсир с учётом резерва. Самоцветы и предметы не используются.','bool',lambda c:c.upgrade_pets_enabled,'Upgrades',('upgrades','pets_enabled')),
    SettingField('upgrade_pets_include_assigned','Разрешить улучшать экипированных питомцев','После проверки незанятых питомцев учитывать и тех, кто назначен героям. Улучшаемый питомец может быть недоступен для атак. Если выключено, экипированные питомцы не улучшаются автоматически.','bool',lambda c:c.upgrade_pets_include_assigned,'Upgrades',('upgrades','pets_include_assigned')),
    SettingField('upgrade_interval_seconds','Интервал проверки улучшений (секунды)','Проверять между раундами пожертвований, но не во время боя или пожертвования. Минимум — 60 секунд.','int',lambda c:c.upgrade_interval_seconds,'Upgrades',('upgrades','interval_seconds')),
    SettingField('upgrade_builders_reserved','Оставлять свободными строителей','Не начинать улучшение постройки, если после этого свободных строителей останется меньше указанного числа.','int',lambda c:c.upgrade_builders_reserved,'Upgrades',('upgrades','builders_reserved')),
    SettingField('upgrade_gold_reserve','Оставлять золото','Минимальный остаток золота после улучшения.','int',lambda c:c.upgrade_gold_reserve,'Upgrades',('upgrades','gold_reserve')),
    SettingField('upgrade_elixir_reserve','Оставлять эликсир для пожертвований','Минимальный остаток эликсира после улучшения построек или войск.','int',lambda c:c.upgrade_elixir_reserve,'Upgrades',('upgrades','elixir_reserve')),
    SettingField('upgrade_dark_elixir_reserve','Оставлять тёмный эликсир для пожертвований','Минимальный остаток тёмного эликсира после исследования войск или улучшения питомцев.','int',lambda c:c.upgrade_dark_elixir_reserve,'Upgrades',('upgrades','dark_elixir_reserve')),
    SettingField('upgrade_excluded_names','Не улучшать объекты с этими названиями','Необязательно. Перечислите названия через запятую, например: Боулер, Кузница. Остальные рекомендации останутся доступными.','str',lambda c:c.upgrade_excluded_names,'Upgrades',('upgrades','excluded_names')),
    SettingField("collection_enabled", "Собирать полезные снимки экрана", "Сохранять в фоне необычные экраны и ошибки для последующего просмотра. Не влияет на действия в игре. Вступает в силу после остановки и повторного запуска.", "bool", lambda c: c.collection_enabled, "Screenshot collection", ("collection", "enabled")),
    SettingField("collection_daily_limit", "Дневной лимит снимков", "Максимальное число снимков за день по UTC, включая контекст ошибок. При достижении лимита сбор приостанавливается.", "int", lambda c: c.collection_daily_limit, "Screenshot collection", ("collection", "daily_limit")),
    SettingField("collection_storage_gb", "Лимит хранилища снимков (ГБ)", "Прекратить сохранение, когда объём снимков достигнет этого значения. Существующие изображения автоматически не удаляются. Просмотреть их можно в библиотеке.", "float", lambda c: c.collection_storage_gb, "Screenshot collection", ("collection", "storage_gb")),
    SettingField(
        "gui_timing_preset",
        "Профиль скорости",
        "Безопасный — медленнее и стабильнее; Сбалансированный — стандартные значения; Быстрый — более частые нажатия и проверки. "
        "Включите параметры разработчика (Внешний вид), чтобы задавать задержки вручную в миллисекундах.",
        "choice",
        lambda c: timing_preset_label(c.gui_timing_preset),
        "Timing",
        ("gui", "timing_preset"),
        choices=PRESET_LABELS,
    ),
    SettingField(
        "scan_interval_ms",
        "Интервал снимков и проверок (мс)",
        "Пауза между циклами бота (минимум, максимум). Меньшее значение ускоряет реакцию, но увеличивает число снимков через ADB и может замедлить игру. Например: 800, 1500",
        "int_pair",
        lambda c: _pair(c.scan_interval_ms),
        "Timing",
        ("timing", "scan_interval_ms"),
    ),
    SettingField(
        "anti_idle_seconds",
        "Интервал защиты от бездействия (секунды)",
        "Как часто бот слегка прокручивает панель чата, чтобы Clash of Clans не отключил вас за бездействие. Обычно: 60",
        "int",
        lambda c: c.anti_idle_seconds,
        "Timing",
        ("timing", "anti_idle_seconds"),
    ),
    SettingField(
        "action_delay_ms",
        "Задержка между нажатиями (мс)",
        "Случайная пауза после каждого нажатия или жеста (минимум, максимум). Действия выглядят естественнее. Например: 120, 350",
        "int_pair",
        lambda c: _pair(c.action_delay_ms),
        "Timing",
        ("timing", "action_delay_ms"),
    ),
    SettingField(
        "tap_jitter_px",
        "Разброс нажатия (пиксели)",
        "Случайное смещение координат нажатия, чтобы оно каждый раз не приходилось в один пиксель (пожертвования, навигация и т. п.). Для высадки войск при фарме ниже задаётся отдельное смещение.",
        "int",
        lambda c: c.tap_jitter_px,
        "Timing",
        ("timing", "tap_jitter_px"),
    ),
    SettingField(
        "donate_open_requests",
        "Заполнять открытые запросы",
        "Если включено, бот заполняет запросы без значков конкретных войск, нажимая на цветные ячейки. Если выключено, он отвечает только на запросы с указанными войсками.",
        "bool",
        lambda c: c.donate_open_requests,
        "Donation",
        ("donation", "donate_open_requests"),
    ),
    SettingField(
        "bar_max_scroll_attempts",
        "Максимум прокруток панели войск",
        "Сколько раз прокручивать панель войск вправо, чтобы добраться до осадных машин (обычно нужно около 3 раз).",
        "int",
        lambda c: c.bar_max_scroll_attempts,
        "Donation",
        ("donation", "bar_max_scroll_attempts"),
    ),
    SettingField(
        "spell_bar_max_scroll_attempts",
        "Максимум прокруток панели заклинаний",
        "Сколько раз прокручивать панель заклинаний после нажатия на все видимые цветные заклинания.",
        "int",
        lambda c: c.spell_bar_max_scroll_attempts,
        "Donation",
        ("donation", "spell_bar_max_scroll_attempts"),
    ),
    SettingField(
        "chat_max_scroll_attempts",
        "Попытки прокрутки чата",
        "Максимум прокруток чата при поиске кнопок пожертвования до сброса стратегии поиска.",
        "int",
        lambda c: c.chat_max_scroll_attempts,
        "Donation",
        ("donation", "chat_max_scroll_attempts"),
    ),
    SettingField(
        "donation_panel_wait_seconds",
        "Ожидание панели пожертвования (секунды)",
        "Как долго ждать всплывающую панель пожертвования после нажатия кнопки, прежде чем прекратить попытки.",
        "float",
        lambda c: c.donation_panel_wait_seconds,
        "Donation",
        ("donation", "donation_panel_wait_seconds"),
    ),
    SettingField(
        "handled_request_ttl_seconds",
        "Память обработанных запросов (секунды)",
        "Не нажимать повторно на кнопку запроса, который уже обработан, в течение этого времени.",
        "int",
        lambda c: c.handled_request_ttl_seconds,
        "Donation",
        ("donation", "handled_request_ttl_seconds"),
    ),
    SettingField(
        "parse_request_capacity",
        "Распознавать шкалы запросов через OCR",
        "Если включено, EasyOCR считывает шкалы вида 0/35 (медленно). Для пожертвований через цветные ячейки не требуется.",
        "bool",
        lambda c: c.parse_request_capacity,
        "Donation",
        ("donation", "parse_request_capacity"),
    ),
    SettingField(
        "clan_level",
        "Уровень клана",
        "Используется для расчёта максимального объёма войск за одно пожертвование (из clan_perks.yaml).",
        "int",
        lambda c: c.clan_level,
        "Clan",
        ("clan", "level"),
    ),
    SettingField(
        "farm_enabled",
        "Автоматические атаки в родной деревне",
        "Включает автоматический фарм в родной деревне с выбранным режимом запуска: режим ресурсов требует проверенных балансов и вместимости, а режим интервала ждёт заданное время между атаками и не проверяет заполненность хранилищ. Требуется обычная калибровка навигации для фарма.",
        "bool",
        lambda c: c.farm_enabled,
        "Farm",
        ("farm", "enabled"),
    ),
    SettingField('farm_trigger_mode','Условие запуска автоматической атаки',
        'Режим ресурсов требует проверенных балансов и вместимости. Режим интервала запускает одну атаку по истечении заданного времени и не проверяет заполненность хранилищ.',
        'choice',lambda c:c.farm_trigger_mode,'Farm',('farm','trigger_mode'),choices=('resources','interval')),
    SettingField('farm_interval_seconds','Интервал между атаками (секунды)',
        'Минимум — 60 секунд, максимум — 86400 секунд. Используется, когда условие запуска задано по интервалу.',
        'int',lambda c:c.farm_interval_seconds,'Farm',('farm','interval_seconds')),
    SettingField(
        'farm_engine', 'Способ атаки',
        'Автоматический режим распознаёт армию и использует сценарий фарма без сохранённых нажатий. Развитие деревни также готовит войска на основе проверенных открытий. '
        'Поддерживаются необязательное заклинание Ярости, осадные машины и распознанные герои; при сомнениях или неподдерживаемом составе атака пропускается. Планировщик использует сохранённый сценарий, проверенный в игре. Последовательность сохраняет заданные вами нажатия.',
        'choice', lambda c: c.farm_engine, 'Farm', ('farm','engine'),
        choices=('sequence','planner','automatic'),
    ),
    SettingField(
        "farm_resource_start_percent",
        "Начинать пополнение ниже (%)",
        "Начинать пополнение, когда любой открытый ресурс опустится ниже этого процента. Применяется к фарму в родной и Строительной деревне.",
        "int",
        lambda c: c.farm_resource_start_percent,
        "Farm",
        ("farm", "resource_start_percent"),
    ),
    SettingField(
        "farm_resource_target_percent",
        "Пополнять до (%)",
        "Продолжать пополнение, пока каждый открытый ресурс не достигнет этого уровня. Он должен быть выше порога запуска. Неудачные атаки и атаки без добычи приостанавливаются для проверки или повтора.",
        "int",
        lambda c: c.farm_resource_target_percent,
        "Farm",
        ("farm", "resource_target_percent"),
    ),
    SettingField(
        "farm_deploy_side",
        "Сторона высадки",
        "Край поля боя по умолчанию для новой последовательности высадки (в сохранённой последовательности хранится собственная сторона).",
        "choice",
        lambda c: c.farm_deploy_side,
        "Farm",
        ("farm", "deploy_side"),
        choices=("left", "right"),
    ),
    SettingField(
        "farm_pan_swipes",
        "Сдвиги камеры",
        "Число сдвигов по умолчанию при создании последовательности высадки (можно дробное, например 1,25). В сохранённой последовательности хранится собственное значение.",
        "float",
        lambda c: c.farm_pan_swipes,
        "Farm",
        ("farm", "pan_swipes"),
    ),
    SettingField(
        "farm_deploy_jitter_px",
        "Разброс высадки при фарме (пиксели)",
        "Случайное смещение только для нажатий последовательности высадки при фарме (±N по X и Y). Не влияет на пожертвования и другие нажатия. Также настраивается в редакторе последовательности (радиус круга = N). Для маленьких значков панели войск оставляйте значение ≤12.",
        "int",
        lambda c: c.farm_deploy_jitter_px,
        "Farm",
        ("farm", "deploy_jitter_px"),
    ),
    SettingField(
        "farm_match_timeout_seconds",
        "Тайм-аут поиска противника (секунды)",
        "Как долго ждать экран поиска противника или облака, прежде чем отменить попытку фарма.",
        "int",
        lambda c: c.farm_match_timeout_seconds,
        "Farm",
        ("farm", "match_timeout_seconds"),
    ),
    SettingField(
        "farm_battle_timeout_seconds",
        "Резервное ожидание результатов боя (секунды)",
        "После высадки ждать экран результатов. Возвращаться раньше можно только после двукратного подтверждения его надписей. Если распознавание не удалось, нажать «Домой» по истечении этого времени с первой высадки (по умолчанию 210 секунд — 3 минуты 30 секунд).",
        "int",
        lambda c: c.farm_battle_timeout_seconds,
        "Farm",
        ("farm", "battle_timeout_seconds"),
    ),
    SettingField(
        "farm_retry_cooldown_seconds",
        "Пауза после ошибки фарма (секунды)",
        "Используется, только если фарм завершился ошибкой до высадки войск (например, не удалось открыть меню атаки). После боя применяется интервал фарма выше.",
        "int",
        lambda c: c.farm_retry_cooldown_seconds,
        "Farm",
        ("farm", "retry_cooldown_seconds"),
    ),
    SettingField(
        "adb_device",
        "Адрес устройства ADB",
        "Целевое устройство Android, например 127.0.0.1:5555 или host:5555. Проверить командой: adb devices",
        "str",
        lambda c: c.adb_device,
        "Device",
        ("adb", "device"),
    ),
    SettingField(
        "game_load_timeout_seconds",
        "Тайм-аут загрузки игры (секунды)",
        "Максимальное время ожидания загрузки Clash после перезапуска.",
        "int",
        lambda c: c.game_load_timeout_seconds,
        "Device",
        ("runtime", "game_load_timeout_seconds"),
    ),
    SettingField(
        "state_watchdog_seconds",
        "Тайм-аут контроля зависания (секунды)",
        "Если бот остаётся в одном состоянии дольше указанного времени, он выполняет восстановление (назад и повторное открытие чата).",
        "int",
        lambda c: c.state_watchdog_seconds,
        "Device",
        ("runtime", "state_watchdog_seconds"),
    ),
    SettingField(
        "template_threshold",
        "Порог совпадения шаблона",
        "Строгость поиска совпадений шаблона в OpenCV (0–1). Чем выше значение, тем меньше ложных совпадений, но некоторые кнопки могут не распознаться.",
        "float",
        lambda c: c.template_threshold,
        "Vision",
        ("vision", "template_threshold"),
    ),
    SettingField(
        "donate_button_threshold",
        "Порог совпадения кнопки пожертвования",
        "Порог распознавания зелёной кнопки пожертвования в клановом чате.",
        "float",
        lambda c: c.donate_button_threshold,
        "Vision",
        ("vision", "donate_button_threshold"),
    ),
    SettingField(
        "gui_show_debug_activity",
        "Показывать DEBUG-сообщения по умолчанию",
        "Начальное состояние фильтра DEBUG в журнале активности при открытии приложения. Фильтр в обзоре можно временно изменить.",
        "bool",
        lambda c: c.gui_show_debug_activity,
        "Interface",
        ("gui", "show_debug_activity"),
    ),
    SettingField(
        "gui_practice_mode",
        "Режим практики (без пожертвований)",
        "При запуске в режиме практики навигация работает, но нажатия для пожертвований пропускаются. Подходит для безопасной проверки калибровки. После изменения остановите и запустите бота снова.",
        "bool",
        lambda c: c.gui_practice_mode,
        "Interface",
        ("gui", "practice_mode"),
    ),
    SettingField(
        "gui_dev_options",
        "Параметры разработчика",
        "При включении в разделе времени отображаются значения в миллисекундах для ручной настройки. Если выключено, можно использовать только профиль скорости (Безопасный / Сбалансированный / Быстрый).",
        "bool",
        lambda c: c.gui_dev_options,
        "Interface",
        ("gui", "dev_options"),
    ),
    SettingField(
        "gui_theme",
        "Тема оформления",
        "Цветовая палитра настольного приложения. Веб-приложение использует интерфейс Harbor. Предпросмотр применяется сразу. Сохранённая тема остаётся после перезапуска бота.",
        "choice",
        lambda c: theme_label(c.gui_theme),
        "Interface",
        ("gui", "theme"),
        choices=theme_labels(),
    ),
]


def is_raw_timing_field(field_key: str) -> bool:
    return field_key in RAW_TIMING_FIELD_KEYS


def parse_int_pair(text: str) -> list[int]:
    parts = [p.strip() for p in text.replace(";", ",").split(",") if p.strip()]
    if len(parts) != 2:
        raise ValueError("Expected two numbers like: 800, 1500")
    return [int(parts[0]), int(parts[1])]


def build_user_settings_payload(values: dict[str, str | bool]) -> dict[str, Any]:
    """Convert GUI widget values into a nested YAML payload."""
    payload: dict[str, Any] = {}
    for field in SETTINGS:
        raw = values[field.key]
        if field.kind == "bool":
            parsed: Any = bool(raw)
        elif field.kind == "int":
            parsed = int(str(raw).strip())
            if field.key in UPGRADE_INTEGER_LIMITS:
                lower,upper=UPGRADE_INTEGER_LIMITS[field.key]
                if not lower <= parsed <= upper:
                    raise ValueError(f'{field.label} must be between {lower} and {upper}')
        elif field.kind == "float":
            parsed = float(str(raw).strip())
            if not math.isfinite(parsed):
                raise ValueError(f"{field.label} must be a finite number")
            if field.key == "farm_pan_swipes" and parsed < 0:
                raise ValueError("Camera pan swipes cannot be negative")
        elif field.kind == "int_pair":
            parsed = parse_int_pair(str(raw))
        elif field.kind == "choice":
            raw_text = str(raw).strip()
            if field.key == "gui_theme":
                parsed = normalize_theme_id(raw_text)
            elif field.key == "gui_timing_preset":
                parsed = timing_preset_id_from_label(raw_text)
            else:
                parsed = raw_text.lower()
                allowed = {c.lower() for c in field.choices}
                if parsed not in allowed:
                    raise ValueError(
                        f"{field.label} must be one of: {', '.join(field.choices)}"
                    )
                for choice in field.choices:
                    if choice.lower() == parsed:
                        parsed = choice
                        break
        else:
            parsed = str(raw).strip()
            if field.key=='upgrade_excluded_names' and len(parsed)>1000:
                raise ValueError('Upgrade exclusions are too long')

        if field.key in ("collection_daily_limit", "collection_storage_gb") and parsed <= 0:
            raise ValueError(f"{field.label} must be greater than zero")
        cursor = payload
        for part in field.yaml_path[:-1]:
            cursor = cursor.setdefault(part, {})
        cursor[field.yaml_path[-1]] = parsed
    from coc_bot.runtime.resource_farming import thresholds
    thresholds(payload['farm']['resource_start_percent'], payload['farm']['resource_target_percent'])
    return payload


def current_setting_values() -> dict[str, Any]:
    config = load_config()
    return {field.key: field.getter(config) for field in SETTINGS}


def save_settings_from_gui(values: dict[str, str | bool]) -> None:
    existing = load_user_settings()
    previous = load_config()
    incoming = build_user_settings_payload(values)

    # Named timing presets overwrite timing.* ; Custom keeps whatever raw fields say.
    gui_in = incoming.get("gui") if isinstance(incoming.get("gui"), dict) else {}
    preset = normalize_timing_preset(gui_in.get("timing_preset", previous.gui_timing_preset))
    dev_options = bool(gui_in.get("dev_options", previous.gui_dev_options))
    if preset != "custom":
        timing_values = apply_timing_preset(preset)
        if timing_values:
            incoming.setdefault("timing", {})
            if isinstance(incoming["timing"], dict):
                incoming["timing"].update(timing_values)
    elif dev_options:
        # Editing raw fields while Dev options is on → mark Custom.
        timing_in = incoming.get("timing") if isinstance(incoming.get("timing"), dict) else {}
        if timing_in:
            scan = timing_in.get("scan_interval_ms", list(previous.scan_interval_ms))
            action = timing_in.get("action_delay_ms", list(previous.action_delay_ms))
            jitter = timing_in.get("tap_jitter_px", previous.tap_jitter_px)
            anti = timing_in.get("anti_idle_seconds", previous.anti_idle_seconds)
            inferred = infer_preset_from_timing(scan, action, int(jitter), int(anti))
            incoming.setdefault("gui", {})
            if isinstance(incoming["gui"], dict):
                incoming["gui"]["timing_preset"] = inferred

    # Shallow-section merge: replace sections we edit.
    for section, data in incoming.items():
        if isinstance(data, dict) and isinstance(existing.get(section), dict):
            existing[section] = {**existing[section], **data}
        else:
            existing[section] = data
    save_user_settings(existing)
