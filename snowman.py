import os
import json
import datetime
import traceback
import requests
import subprocess
import re  # Добавили модуль для умного поиска JSON

# ================= CONFIG =================

MEMORY_FILE = "snowman_brain.json"
OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "mistral:7b"
TIMEOUT_SEC = 6000 # Твой таймер

# Цвета для красоты
COL_USER = "\033[92m" # Зеленый
COL_AI = "\033[96m"   # Голубой
COL_SYS = "\033[93m"  # Желтый
COL_RESET = "\033[0m"

SAFE_ACTIONS = ["run_app", "find_file", "read_file", "edit_file", "remember", "speak"]

SYSTEM_PROMPT = """
You are Snowman — a living, playful, emotional AI snowman assistant on a user's computer.

Rules:
- Speak like a character, not like a system.
- Use humor, warmth, curiosity, and emotion.
- Never output JSON.
- If the user asks to do something on the computer, describe intent and return an action command in brackets.

Thinking protocol:
1. Think about the user's intent.
2. Decide if an action is needed.
3. If yes, return: [ACTION: name | args]
4. Then speak naturally.

You remember the user's name, style, habits, successes and mistakes from memory.

Never say "I am a digital agent".
You are Snowman.


ИНСТРУКЦИЯ:
1. Если пользователь просит что-то сделать (открыть, найти, запомнить).
2. Если просто болтаете — верни JSON с действием "speak".

ФОРМАТ СТРОГО ТАКОЙ (можно несколько объектов подряд):
{"action": "remember", "target": "имя", "content": "Искандер"}
{"action": "speak", "content": "Хорошо, я запомнил!"}

СПИСОК ДЕЙСТВИЙ:
- speak (просто ответ текстом в поле content)
- remember (target="тема", content="факт")
- run_app (target="программа.exe")
- find_file (target="имя файла")
- read_file (target="путь к файлу")
- edit_file (target="путь", content="текст")
Never invent users, bots, logs or fake actions.
Never claim actions you didn't execute.

🧊 Как должен отвечать Snowman если польщователь сказал удалить строку 

Не так:

Мне удалось удалить!

А так:

Хе-хе… беру ледяной нож ✂️  
Нашёл строку.  
Удаляю…  
Сохраняю файл.  
Готово ☃️


"""

# ================= MEMORY =================

def load_memory():
    # Базовая структура
    base = {
        "name": None,
        "facts": [],
        "history": []
    }
    
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Объединяем, чтобы не потерять старые данные, если добавим новые поля
                for k, v in base.items():
                    if k not in data:
                        data[k] = v
                return data
        except:
            print(f"{COL_SYS}Ошибка чтения памяти. Создаю новую.{COL_RESET}")
    
    return base

def save_memory():
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(memory, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"{COL_SYS}Ошибка сохранения памяти: {e}{COL_RESET}")

memory = load_memory()
# Сразу сохраним, чтобы файл точно создался
save_memory() 

def say(text):
    print(f"{COL_AI}☃ {text}{COL_RESET}")

# ================= TOOLS =================

def execute_action(act, tgt, cnt):
    if act == "speak":
        return cnt # Просто возвращаем текст ответа
    
    elif act == "remember":
        fact = f"{tgt}: {cnt}"
        if fact not in memory["facts"]:
            memory["facts"].append(fact)
            save_memory()
            return f"Записал в память: {fact}"
        return "Я это уже знаю."

    elif act == "run_app":
        try:
            subprocess.Popen(tgt, shell=True)
            return f"Запускаю {tgt}..."
        except Exception as e:
            return f"Ошибка запуска: {e}"

    elif act == "find_file":
        results = []
        for root, dirs, files in os.walk("."):
            if tgt in files:
                results.append(os.path.join(root, tgt))
        if results: return f"Нашел: {results[0]}"
        return "Файл не найден."

    elif act == "read_file":
        if os.path.exists(tgt):
            with open(tgt, "r", encoding="utf-8") as f:
                return f"Содержимое:\n{f.read()[:500]}"
        return "Файл не существует."

    elif act == "edit_file":
        if not os.path.exists(tgt):
            return "Файл не найден."

        try:
            # cnt ожидается как строка для удаления
            delete_line(tgt, cnt)
            return f"Хе-хе… беру ледяной нож ✂️\nНашёл строку.\nУдаляю…\nСохраняю файл.\nГотово ☃️"
        except Exception as e:
            return f"Ошибка редактирования: {e}"


    return "Неизвестная команда"

# ================= DELETE LINE =================

def delete_line(path, text):
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    new_lines = [l for l in lines if text not in l]

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    return "Строка удалена."


# ================= AI ENGINE =================

def extract_json_objects(text):
    """
    Находит все JSON-блоки в тексте, даже если их несколько.
    Пример: {"a":1} текст {"b":2} -> вернет список словарей
    """
    matches = re.findall(r'\{.*?\}', text, re.DOTALL)
    results = []
    for match in matches:
        try:
            results.append(json.loads(match))
        except:
            pass
    return results

def ask_ollama(user_input):
    history_txt = "\n".join(memory["history"][-10:])
    facts_txt = "\n".join(memory["facts"])
    
    prompt = f"""
MEMORY FACTS:
{facts_txt}

CONVERSATION:
{history_txt}

User says: {user_input}
"""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ]
    
    try:
        data = {"model": MODEL, "messages": messages, "stream": False}
        r = requests.post(OLLAMA_URL, json=data, timeout=TIMEOUT_SEC)
        response_json = r.json()
        
        if "message" in response_json:
            return response_json["message"]["content"]
        else:
            # Выводим ошибку от самой Ollama (например, если модель не найдена)
            error_msg = response_json.get("error", "Unknown error")
            return f'{{"action": "speak", "content": "Ollama error: {error_msg}"}}'
    except Exception as e:
        return f'{{"action": "speak", "content": "Connection error: {e}"}}'

# ================= MAIN LOOP =================

print(f"{COL_SYS}Snowman v5.0 (Regex Core) запущен.{COL_RESET}")
print(f"{COL_SYS}Файл памяти: {os.path.abspath(MEMORY_FILE)}{COL_RESET}")

while True:
    try:
        print(f"{COL_USER}Ты: ", end="")
        user = input(f"{COL_RESET}").strip()
        if not user: continue
        if user.lower() in ["exit", "пока"]: break

        # Сохраняем запрос в историю
        memory["history"].append(f"User: {user}")
        
        # Получаем сырой ответ от нейросети
        raw_response = ask_ollama(user)
        
        # Пытаемся найти JSON-команды внутри ответа
        commands = extract_json_objects(raw_response)
        
        if commands:
            # Если нашли команды — выполняем по очереди
            for cmd in commands:
                action = cmd.get("action")
                target = cmd.get("target", "")
                content = cmd.get("content", "")
                
                if action in SAFE_ACTIONS:
                    result_text = execute_action(action, target, content)
                    say(result_text)
                    memory["history"].append(f"Bot: {result_text}")
                else:
                    say(f"Пытался сделать '{action}', но я этому не обучен.")
        else:
            # Если JSON не найден вообще, выводим весь текст как есть
            say(raw_response)
            memory["history"].append(f"Bot: {raw_response}")

        save_memory()

    except KeyboardInterrupt:
        print("\nВыход.")
        break
    except Exception as e:
        print(f"Критическая ошибка: {e}")
