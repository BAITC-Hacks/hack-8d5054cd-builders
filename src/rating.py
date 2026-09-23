"""Прозрачный рейтинг полноты карточки без вызовов AI и внешних сервисов."""

from __future__ import annotations

import re
from typing import Any

from .models import CARD_FIELDS


# Контекст и потребность вместе дают 20 баллов; контакт и формат — ещё 10.
FIELD_WEIGHTS: dict[str, int] = {
    "context": 10,
    "need": 10,
    "data": 20,
    "expected_result": 15,
    "success_criteria": 15,
    "constraints": 10,
    "users": 10,
    "contact": 5,
    "collaboration_format": 5,
}

# Короткий ответ даёт половину веса. Это делает подсказки полезными и для
# частично заполненных карточек, сохраняя формулу детерминированной.
MIN_DETAIL_LENGTH: dict[str, int] = {
    "context": 35,
    "need": 20,
    "data": 15,
    "expected_result": 20,
    "success_criteria": 20,
    "constraints": 14,
    "users": 10,
    "contact": 5,
    "collaboration_format": 12,
}

GROUPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("Контекст и потребность", "context_need", ("context", "need")),
    ("Данные и материалы", "data", ("data",)),
    ("Ожидаемый результат", "expected_result", ("expected_result",)),
    ("Критерии успеха", "success_criteria", ("success_criteria",)),
    ("Ограничения", "constraints", ("constraints",)),
    ("Пользователи", "users", ("users",)),
    ("Связь с бизнесом", "business_link", ("contact", "collaboration_format")),
)

IMPROVEMENT_HINTS: dict[str, str] = {
    "context": "Опишите, что происходит сейчас и в каком процессе возникает задача.",
    "need": "Сформулируйте, что именно нужно изменить или решить.",
    "data": "Назовите доступные материалы или источник; если данных нет, опишите, что и как соберёте.",
    "expected_result": "Назовите конкретный результат, который должна подготовить команда.",
    "success_criteria": "Укажите порог метрики или конкретный сценарий и способ проверки, по которым бизнес примет результат.",
    "constraints": "Укажите сроки, доступы, технологии или другие границы работы.",
    "users": "Уточните, кто будет пользоваться решением или результатом.",
    "contact": "Укажите человека или канал связи со стороны бизнеса.",
    "collaboration_format": "Опишите, как часто и в каком формате команда сможет получать обратную связь.",
}

PLACEHOLDERS = {
    "н д",
    "n a",
    "tbd",
    "todo",
    "не указано",
    "неизвестно",
    "пока неизвестно",
    "уточняется",
    "нет данных",
    "нет информации",
    "не определено",
    "не предоставлено",
    "не знаю",
    "не знаем",
}

# Только узнаваемые заглушки, без попытки оценить смысл или качество ответа.
# Полное совпадение сохраняет полезные дополнения: «Данных нет, соберём опрос».
DEFERRED_ANSWER = re.compile(
    r"(?:(?:данные|контакт|сроки|критерии|информацию|это) )?"
    r"(?:уточним|уточню|уточнить|определим|добавим|сообщим|обсудим|согласуем)"
    r"(?: (?:позже|потом|позднее|впоследствии))?"
    r"(?: (?:после встречи|на встрече|после созвона|на созвоне|"
    r"после обсуждения|после согласования))?"
    r"(?: с бизнесом)?"
)

# Узкие проверки известных формулировок, а не доказательство наличия данных
# или смысловой проверяемости критерия. Остальные ответы оцениваются как раньше.
DATA_ABSENCE = re.compile(
    r"\b(?:нет\b[^,;.!?]*\b(?:данных|материалов|документов|примеров|информации)|"
    r"(?:данных|материалов|документов|примеров|информации)\b[^,;.!?]*\bнет|"
    r"(?:данные|материалы|документы|примеры|информация)\b[^,;.!?]*\b"
    r"(?:отсутствуют|отсутствует|недоступны|недоступна|не собраны|не предоставлены)|"
    r"нет доступа к (?:данным|материалам|документам|информации)|"
    r"не (?:готовы|можем) (?:передать|предоставить) "
    r"(?:данные|материалы|документы|информацию)|"
    r"ничего (?:пока )?нет)\b"
)

# После сообщения об отсутствии отбрасываем только общие обещания. Источники
# не ограничены словарём форматов: «есть журнал смен» и «соберём фото витрин»
# тоже сохраняются. Неизвестные формулировки могут потребовать проверки человеком.
DATA_PROMISE_WORDS = set(
    "а и но пока еще уже сейчас позже потом позднее впоследствии возможно вероятно "
    "наверное будут будет появятся появится появление мы у нас их они это все "
    "есть имеется имеются доступно доступны доступные нужно надо необходимо хотим "
    "планируем планируется получить получим собрать соберем собирать сбор "
    "предоставим предоставят уточним уточнить узнаем запросим найдем найти "
    "данные данных материалы материалов информация информации источник источники "
    "какие какие-то что что-то как нибудь скоро со временем после встречи "
    "обсуждения согласования с бизнесом об этом будем думать решим вопрос "
    "не нет через в на за день дня дней неделю недели недель месяц месяца "
    "месяцев первый первой следующей следующий этапе этап срок сроки решено".split()
)
VAGUE_CRITERIA_WORDS = set(
    "нужно надо необходимо хотим хочется хочу чтобы все всем всё будет будут было "
    "была были быть стало станет работало работали работал работает работают "
    "работать должно должна должны должен и а но или очень более максимально "
    "хорошо лучше удобно удобнее комфортно качественно качественнее "
    "быстро быстрее эффективно эффективнее успешно стабильно надежно понятно "
    "интуитивно просто идеально отлично нормально без проблем "
    "пользователям пользоваться сервисом системой решением продуктом приложение "
    "сервис система решение продукт на процентов процент процента раз раза "
    "всегда всем полностью достаточно заметно результат результатом довольны".split()
)
VAGUE_QUALITY_WORDS = set(
    "хорошо лучше удобно удобнее комфортно качественно качественнее быстро быстрее "
    "эффективно эффективнее успешно стабильно надежно понятно просто идеально "
    "отлично нормально проблем довольны".split()
)
BARE_METRIC_WISH = re.compile(
    r"(?:(?:нужно|необходимо|хотим) )?"
    r"(?:повысить|увеличить|улучшить|снизить|уменьшить) "
    r"(?:(?:заметно|значительно) )?"
    r"(?:конверсию|точность|скорость обработки|время обработки|количество ошибок|долю ошибок)"
    r"(?: (?:заказов|прогноза|модели|заявок))?"
)


def _word_text(text: str) -> str:
    return " ".join(re.findall(r"[^\W_]+", text.casefold().replace("ё", "е")))


def _data_is_only_absence(text: str) -> bool:
    normalized = text.casefold().replace("ё", "е")
    if not DATA_ABSENCE.search(normalized):
        return False
    clauses = re.split(r"[,;.!?]|\b(?:но|зато|однако)\b", normalized)
    for clause in clauses:
        if DATA_ABSENCE.search(clause) or _is_empty_answer(clause):
            continue
        words = set(_word_text(clause).split())
        details = {word for word in words - DATA_PROMISE_WORDS if not word.isdigit()}
        if details:
            return False
    return True


def _criteria_cap(text: str) -> int:
    normalized = _word_text(text)
    words = {word for word in normalized.split() if not word.isdigit()}
    if words & VAGUE_QUALITY_WORDS and words <= VAGUE_CRITERIA_WORDS:
        return 0
    if BARE_METRIC_WISH.fullmatch(normalized):
        return FIELD_WEIGHTS["success_criteria"] // 2
    return FIELD_WEIGHTS["success_criteria"]


def _clean_text(value: Any) -> str:
    # Значение поля карточки — текст. Объект/список из некорректного AI JSON
    # не должен превращаться в заполненное поле через str(value).
    if not isinstance(value, str):
        return ""
    return " ".join(value.split()).strip()


def _is_empty_answer(text: str) -> bool:
    # Пунктуация и регистр не меняют статус «Не указано.» или «Н/Д».
    words = re.findall(r"[^\W_]+", text.casefold(), flags=re.UNICODE)
    normalized = " ".join(words)
    if not normalized or normalized in PLACEHOLDERS:
        return True
    if DEFERRED_ANSWER.fullmatch(normalized):
        return True

    compact = "".join(words)
    if re.fullmatch(r"(.)\1{3,}", compact):
        return True
    # Простой повтор короткого фрагмента и известные клавиатурные заглушки.
    if re.fullmatch(r"(.{2,3})\1{2,}", compact):
        return True
    if compact in {"asdf", "asdfgh", "qwer", "qwerty", "qwertyuiop", "йцукен", "йцукенгшщз", "фыва", "фывапр"}:
        return True
    # Адреса и ссылки могут законно повторять имя: team@team.team.
    if "@" not in text and "://" not in text and len(words) > 1 and len(set(words)) == 1:
        return True
    return False


def _earned_points(field: str, value: Any) -> int:
    text = _clean_text(value)
    if not text or _is_empty_answer(text):
        return 0
    if field == "data" and _data_is_only_absence(text):
        return 0
    weight = FIELD_WEIGHTS[field]
    if field == "success_criteria":
        weight = min(weight, _criteria_cap(text))
    if len(text) < MIN_DETAIL_LENGTH[field]:
        return min(weight, FIELD_WEIGHTS[field] // 2)
    return weight


def calculate_rating(card: dict[str, Any]) -> dict[str, Any]:
    """Вернуть балл, уровень, расшифровку и улучшения для карточки.

    Функция чистая: результат зависит только от переданных полей, не меняет
    карточку и не обращается к Streamlit, файлам, AI или сети. Проверяются
    заполненность, длина, явные заглушки и несколько известных формулировок
    отсутствия данных / общих пожеланий; смысловое качество не доказывается.
    """
    per_field = {
        field: _earned_points(field, card.get(field, ""))
        for field in FIELD_WEIGHTS
    }
    score = sum(per_field.values())
    if score <= 39:
        level = "Черновик"
    elif score <= 69:
        level = "Рабочая"
    elif score <= 89:
        level = "Готовая"
    else:
        level = "Приоритетная"

    breakdown = []
    for label, key, fields in GROUPS:
        earned = sum(per_field[field] for field in fields)
        possible = sum(FIELD_WEIGHTS[field] for field in fields)
        breakdown.append({"key": key, "label": label, "earned": earned, "possible": possible})

    improvements = []
    for field, weight in FIELD_WEIGHTS.items():
        earned = per_field[field]
        if earned == weight:
            continue
        improvements.append(
            {
                "field": field,
                "label": CARD_FIELDS[field],
                "potential_points": weight - earned,
                "hint": IMPROVEMENT_HINTS[field],
            }
        )
    improvements.sort(key=lambda item: (-item["potential_points"], item["label"]))

    return {
        "score": score,
        "level": level,
        "breakdown": breakdown,
        "improvements": improvements,
    }
