import os
import shutil
from aiogram import Bot, Router, F
from aiogram.filters import Command
from aiogram.types import Message, InputFile, FSInputFile
from aiogram.fsm.context import FSMContext
import asyncio
from aiogram import Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ContentType, ReplyKeyboardMarkup, KeyboardButton
from dotenv import load_dotenv
from pathlib import Path
from PIL import Image
from PyPDF2 import PdfMerger
from typing import List
import aiofiles
from uuid import uuid4

load_dotenv(dotenv_path=".env")

TG_TOKEN = os.getenv("TG_TOKEN")

bot = Bot(token=TG_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()

BASE_PATH = "user_files"
RESULTS_PATH = "results"

os.makedirs(BASE_PATH, exist_ok=True)
os.makedirs(RESULTS_PATH, exist_ok=True)

kb = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="Объединить файлы"),
        ]
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
    selective=True,
)

@router.message(Command(commands=["start"]))
async def send_welcome(message: Message):
    await message.answer(
        "Привет! Я бот для обработки файлов. Отправьте файл для обработки.", reply_markup=kb
    )

@router.message(Command(commands=["help"]))
async def send_help(message: Message):
    await message.answer(
        "Я могу принимать и обрабатывать файлы. Просто отправьте файл или фото, и я обработаю их для вас."
    )

user_file_counters = {}
MAX_FILES = 50  # Максимальное количество файлов
MAX_DIR_SIZE_MB = 100  # Максимальный размер директории пользователя (в мегабайтах)


def get_directory_size(directory: str) -> int:
    """Получить размер директории в байтах."""
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(directory):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_size += os.path.getsize(fp)
    return total_size


async def check_user_limits(user_dir: str) -> bool:
    """Проверить, не превышены ли ограничения по количеству файлов и размеру директории."""
    # Проверка количества файлов
    file_count = len(os.listdir(user_dir))
    if file_count >= MAX_FILES:
        return False

    # Проверка размера директории
    dir_size_mb = get_directory_size(user_dir) / (1024 * 1024)
    if dir_size_mb >= MAX_DIR_SIZE_MB:
        return False

    return True


@router.message(F.content_type == ContentType.DOCUMENT)
async def save_document(message: Message):
    user_id = message.from_user.id
    user_dir = os.path.join(BASE_PATH, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    if not await check_user_limits(user_dir):
        await message.reply("Превышены ограничения: не более 50 файлов и 100 МБ на пользователя.")
        return

    counter = user_file_counters.get(user_id, 0) + 1
    user_file_counters[user_id] = counter

    document = message.document
    file_path = os.path.join(user_dir, f"{counter:03d}_{uuid4()}_{document.file_name}")

    file_info = await bot.get_file(document.file_id)
    file_data = await bot.download_file(file_info.file_path)

    async with aiofiles.open(file_path, mode="wb") as f:
        await f.write(file_data.read())

    await message.reply(f"Файл успешно добавлен!")


@router.message(F.content_type == ContentType.PHOTO)
async def save_photo(message: Message):
    user_id = message.from_user.id
    user_dir = os.path.join(BASE_PATH, str(user_id))
    os.makedirs(user_dir, exist_ok=True)

    if not await check_user_limits(user_dir):
        await message.reply("Превышены ограничения: не более 50 файлов и 100 МБ на пользователя.")
        return

    counter = user_file_counters.get(user_id, 0) + 1
    user_file_counters[user_id] = counter

    photo = message.photo[-1]
    original_file_path = os.path.join(user_dir, f"{counter:03d}_{uuid4()}_{photo.file_id}.png")
    converted_file_path = os.path.join(user_dir, f"{counter:03d}_{uuid4()}_{photo.file_id}.jpg")

    file_info = await bot.get_file(photo.file_id)
    file_data = await bot.download_file(file_info.file_path)

    # Сохраняем оригинальное изображение временно
    async with aiofiles.open(original_file_path, mode="wb") as f:
        await f.write(file_data.read())

    try:
        with Image.open(original_file_path) as img:
            img = img.convert("RGB")
            img.save(converted_file_path, format="JPEG")
        os.remove(original_file_path)
    except Exception as e:
        await message.reply(f"Ошибка при конвертации изображения: {e}")
        return

    await message.reply(f"Фото успешно добавлено как JPG!")


async def convert_to_pdf(in_dir: str, out_file: str):
    """Конвертация изображений и объединение PDF-файлов в один PDF."""
    KNOWN_IMAGE_EXTS = ('.jpg', '.jpeg', '.png')
    pdf_merger = PdfMerger()
    images = []

    entries = os.listdir(in_dir)

    for entry in entries:
        _, ext = os.path.splitext(entry)
        path_name = os.path.join(in_dir, entry)

        if ext.lower() in KNOWN_IMAGE_EXTS:
            img = Image.open(path_name)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            temp_pdf_path = os.path.splitext(path_name)[0] + ".pdf"
            img.save(temp_pdf_path, format='PDF')
            images.append(temp_pdf_path)
            img.close()

        elif ext.lower() == '.pdf':
            pdf_merger.append(path_name)

    for img_pdf in images:
        pdf_merger.append(img_pdf)

    with open(out_file, 'wb') as f:
        pdf_merger.write(f)
    pdf_merger.close()

    for img_pdf in images:
        os.remove(img_pdf)

    return out_file if os.path.exists(out_file) else None


@router.message(F.text == "Объединить файлы")
async def handle_message(message: Message):
    user_id = message.from_user.id
    user_folder = os.path.join(BASE_PATH, str(user_id))
    result_folder = os.path.join(RESULTS_PATH, str(user_id))
    os.makedirs(result_folder, exist_ok=True)

    result_pdf = os.path.join(result_folder, "result.pdf")
    final_pdf = await convert_to_pdf(user_folder, result_pdf)

    if final_pdf and os.path.exists(final_pdf):
        await message.answer_document(FSInputFile(final_pdf))
        shutil.rmtree(user_folder)
        shutil.rmtree(result_folder)
    else:
        await message.reply("Не удалось создать PDF. Проверьте, загружены ли изображения.")

@router.message()
async def unsupported_content(message: Message):
    await message.reply("Я могу сохранять только документы и фотографии.")

async def main():
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
