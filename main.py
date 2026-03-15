from fastapi import FastAPI, Form, File, UploadFile, Depends
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from io import BytesIO
from PIL import Image
import os
import uuid
from fastapi import Request
from fastapi import FastAPI, Request, Form, HTTPException, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import random
import string
import uuid
from datetime import datetime
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import httpx
from typing import Annotated
from fastapi import Query
from base64 import b64encode
from fastapi.responses import RedirectResponse
from fastapi import HTTPException, File, UploadFile, Form
from fastapi.responses import JSONResponse
from PIL import Image
import os
import uuid



app = FastAPI()

# Устанавливаем путь для статических файлов
app.mount("/static", StaticFiles(directory="static"), name="static")

# Настройка шаблонов
templates = Jinja2Templates(directory="templates")

# Папка для сохранения комиксов
COMIC_DIR = 'static/comics'
UPLOAD_DIR = 'static/images'

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/get_images")
async def get_images():
    # Список всех изображений в каталоге
    images = os.listdir(UPLOAD_DIR)
    images = [image for image in images if image.endswith(('jpg', 'jpeg', 'png', 'gif'))]  # Убедитесь, что фильтруете изображения по расширению
    return images

@app.get("/comics", response_class=HTMLResponse)
async def comics_page(request: Request):
    # Здесь будет логика для загрузки списка комиксов
    comics = os.listdir(COMIC_DIR)
    comics = sorted(comics, key=lambda x: os.path.getctime(os.path.join(COMIC_DIR, x)), reverse=True)

    comic_data = []
    for comic in comics:
        comic_folder = os.path.join(COMIC_DIR, comic)
        metadata_path = os.path.join(comic_folder, "metadata.txt")
        
        if os.path.exists(metadata_path):
            with open(metadata_path, "r") as f:
                metadata = {}
                for line in f:
                    key, value = line.strip().split(": ")
                    metadata[key] = value
            comic_data.append({"uuid": comic, "title": metadata.get("Title", "Без названия"), "author": metadata.get("Author", "Не указан")})
        else:
            comic_data.append({"uuid": comic, "title": "Без названия", "author": "Не указан"})

    return templates.TemplateResponse("comics.html", {"request": request, "comics": comic_data})

@app.get("/imgur", response_class=HTMLResponse)
async def imgur_page(request: Request):
    # Здесь будет логика для imgur или другой платформы
    return templates.TemplateResponse("imgur.html", {"request": request})
# Страница для создания нового комикса
@app.get("/create", response_class=HTMLResponse)
async def create_comic(request: Request):
    return templates.TemplateResponse("create_comic.html", {"request": request})

@app.get("/comic/{comic_id}", response_class=HTMLResponse)
async def view_comic(request: Request, comic_id: str):
    comic_folder = os.path.join(COMIC_DIR, comic_id)
    
    if not os.path.exists(comic_folder):
        return {"error": "Комикс не найден!"}
    
    # Список изображений (отсортирован по имени)
    images = sorted([img for img in os.listdir(comic_folder) if img.endswith('.jpg')], key=lambda x: int(x.split('.')[0]))
    
    # Чтение метаданных
    metadata_path = os.path.join(comic_folder, "metadata.txt")
    metadata = {}
    if os.path.exists(metadata_path):
        with open(metadata_path, "r") as f:
            for line in f:
                key, value = line.strip().split(": ")
                metadata[key] = value
    
    return templates.TemplateResponse("view_comic.html", {"request": request, "comic_id": comic_id, "images": images, "metadata": metadata})

# ────────────────────────────────────────────────
# CAPTCHA генерация
# ────────────────────────────────────────────────

CAPTCHA_LENGTH = 6
CAPTCHA_WIDTH = 220
CAPTCHA_HEIGHT = 80
CAPTCHA_FONT_SIZE = 42
MIN_CHAR_DISTANCE = 28       # минимальное расстояние между символами по X
NOISE_LINES_COUNT = 10
NOISE_DOTS_COUNT = 80
captcha_store: dict[str, str] = {}  # Store CAPTCHA text temporarily

def generate_captcha_text(length: int = CAPTCHA_LENGTH) -> str:
    """Генерирует текст CAPTCHA без визуально похожих символов"""
    # Убрали 0/O, 1/I/l, 5/S, 8/B — самые проблемные комбинации
    ambiguous = "0O1Il5S8B"
    allowed = "".join(c for c in string.ascii_uppercase + string.digits if c not in ambiguous)
    
    return ''.join(random.choice(allowed) for _ in range(length))


def create_captcha_image(text: str) -> BytesIO:
    """
    Создаёт искажённое изображение CAPTCHA с шумом.
    Возвращает BytesIO с PNG.
    """
    # Светлый фон (можно параметризовать)
    img = Image.new('RGB', (CAPTCHA_WIDTH, CAPTCHA_HEIGHT), color=(245, 245, 248))
    draw = ImageDraw.Draw(img)

    # ─── Попытка загрузить нормальный шрифт ───────────────────────
    try:
        font = ImageFont.truetype("arial.ttf", CAPTCHA_FONT_SIZE)
    except (IOError, OSError):
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", CAPTCHA_FONT_SIZE)
        except (IOError, OSError):
            font = ImageFont.load_default()
            # Если default — уменьшаем размер, он очень мелкий
            font = ImageFont.load_default(size=36) if hasattr(ImageFont.load_default, 'size') else font

    # ─── Рисуем искажённые символы ────────────────────────────────
    for i, char in enumerate(text):
        # Случайное смещение и небольшой поворот
        x = 15 + i * MIN_CHAR_DISTANCE + random.randint(-8, 8)
        y = 12 + random.randint(-14, 14)

        # Случайный цвет текста (тёмные оттенки, но читаемые)
        color = (
            random.randint(40, 140),
            random.randint(40, 140),
            random.randint(100, 220)
        )

        # Можно добавить rotate (но тогда нужна промежуточная картинка)
        draw.text((x, y), char, font=font, fill=color)

    # ─── Шум: линии ───────────────────────────────────────────────
    for _ in range(NOISE_LINES_COUNT):
        x1, y1 = random.randint(0, CAPTCHA_WIDTH), random.randint(0, CAPTCHA_HEIGHT)
        x2, y2 = random.randint(0, CAPTCHA_WIDTH), random.randint(0, CAPTCHA_HEIGHT)
        color = (
            random.randint(120, 180),
            random.randint(120, 180),
            random.randint(140, 200)
        )
        draw.line((x1, y1, x2, y2), fill=color, width=random.randint(1, 2))

    # ─── Шум: точки / мелкий мусор ────────────────────────────────
    for _ in range(NOISE_DOTS_COUNT):
        x = random.randint(0, CAPTCHA_WIDTH)
        y = random.randint(0, CAPTCHA_HEIGHT)
        r = random.randint(1, 2)
        color = (
            random.randint(100, 180),
            random.randint(100, 180),
            random.randint(120, 200)
        )
        draw.ellipse((x-r, y-r, x+r, y+r), fill=color)

    # ─── Сохраняем в память ───────────────────────────────────────
    buffered = BytesIO()
    img.save(buffered, format="PNG", optimize=True)
    buffered.seek(0)

    return buffered

# ────────────────────────────────────────────────
# Эндпоинты CAPTCHA
# ───────────────────────────

@app.get("/imgur", response_class=HTMLResponse)
async def imgur_page(request: Request):
    # Здесь будет логика для страницы imgur (или что-то аналогичное)
    return templates.TemplateResponse("imgur.html", {"request": request})

@app.get("/captcha", response_class=StreamingResponse)
async def get_captcha_image(captcha_id: str = Query(None)):
    if captcha_id and captcha_id in captcha_store:
        text = captcha_store[captcha_id]
    else:
        text = generate_captcha_text()
        captcha_id = str(uuid.uuid4())
        captcha_store[captcha_id] = text

    image_io = create_captcha_image(text)
    return StreamingResponse(image_io, media_type="image/png")

@app.get("/captcha/id", response_class=JSONResponse)
async def get_captcha_id():
    captcha_id = str(uuid.uuid4())
    captcha_store[captcha_id] = generate_captcha_text()
    return {"captcha_id": captcha_id}

@app.get("/captcha/data")
async def get_captcha_data():
    text = generate_captcha_text()
    captcha_id = str(uuid.uuid4())
    captcha_store[captcha_id] = text

    image_io = create_captcha_image(text)
    image_bytes = image_io.getvalue()
    base64_image = b64encode(image_bytes).decode("utf-8")

    return {
        "captcha_id": captcha_id,
        "image": f"data:image/png;base64,{base64_image}"
    }

@app.post("/upload_comic")
async def upload_comic(
    captcha_id: Annotated[str, Form()],  # No default value, must come first
    captcha_user_input: Annotated[str, Form()],  # No default value, must come second
    title: str = Form(...),
    author: str = Form(...),
    images: list[UploadFile] = File(...),  # Default value, comes after
):
    # Проверяем CAPTCHA
    correct_answer = captcha_store.get(captcha_id)
    if not correct_answer:
        raise HTTPException(400, "Captcha не найден или истёк")
    if captcha_user_input.strip().upper() != correct_answer.upper():
        raise HTTPException(400, "Неверный код с картинки")

    # Удаляем капчу после проверки
    del captcha_store[captcha_id]

    # Генерируем уникальный ID для комикса
    comic_id = str(uuid.uuid4())
    comic_folder = os.path.join(COMIC_DIR, comic_id)
    os.makedirs(comic_folder)

    # Сохраняем изображения
    for idx, image in enumerate(images):
        img = Image.open(image.file)
        img = img.convert("RGB")
        img.save(os.path.join(comic_folder, f"{idx}.jpg"), "JPEG", quality=75)  # Сжимаем изображение

    # Сохраняем метаданные
    with open(os.path.join(comic_folder, "metadata.txt"), "w") as f:
        f.write(f"Title: {title}\n")
        f.write(f"Author: {author}\n")

    # Перенаправляем на страницу с только что загруженным комиксом
    return RedirectResponse(url=f"/comic/{comic_id}", status_code=303)
MAX_FILE_SIZE = 5 * 1024 * 1024  # Максимальный размер файла 5MB

@app.get("/imgur", response_class=HTMLResponse)
async def imgur_page(request: Request):
    # Получаем список всех изображений
    images = get_all_images()
    return templates.TemplateResponse("imgur.html", {"request": request, "images": images})
@app.post("/upload_image")
async def upload_image(
    captcha_id: str = Form(...),
    captcha_user_input: str = Form(...),
    image: UploadFile = File(...),
):
    """Загружает изображение с сжатием и ограничением размера файла"""
    
    # Проверка капчи
    correct_answer = captcha_store.get(captcha_id)
    if not correct_answer:
        raise HTTPException(status_code=400, detail="Captcha expired or invalid")
    if captcha_user_input.strip().upper() != correct_answer.upper():
        raise HTTPException(status_code=400, detail="Captcha mismatch")

    # Удаление капчи после использования
    del captcha_store[captcha_id]

    # Проверяем размер файла
    if image.size > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File size exceeds the maximum limit of 5MB.")

    # Проверяем тип изображения
    if image.content_type not in ["image/jpeg", "image/png", "image/gif"]:
        raise HTTPException(status_code=400, detail="Only JPG, PNG, and GIF images are allowed.")

    # Сохранение изображения с сжатием
    img = Image.open(image.file)
    img_format = img.format.lower()

    # Генерация уникального имени для изображения
    filename = f"{uuid.uuid4()}.{img_format}"
    img_path = os.path.join(UPLOAD_DIR, filename)

    # Сжимаем изображение, если это не PNG (PNG обычно не нужно сжимать дополнительно)
    if img_format in ['jpeg', 'jpg']:
        # Сжимаем изображение для уменьшения размера
        img = img.convert("RGB")  # Преобразуем в RGB, если изображение имеет другой цветовой режим
        img.save(img_path, "JPEG", quality=50)  # Качество сжатия 85 (можно настроить)

    elif img_format == 'png':
        img.save(img_path, "PNG")  # Для PNG не применяем сжатие

    elif img_format == 'gif':
        img.save(img_path, "GIF")  # Для GIF не применяем сжатие

    return JSONResponse(content={"message": "Image uploaded successfully!", "filename": filename})