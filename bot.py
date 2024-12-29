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

# Загрузка токена из .env
load_dotenv(dotenv_path=".env")

TG_TOKEN = os.getenv("TG_TOKEN")

bot = Bot(token=TG_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()

# Папки
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

@router.message(F.content_type == ContentType.DOCUMENT)
async def save_document(message: Message):
    user_id = message.from_user.id
    user_dir = os.path.join(BASE_PATH, str(user_id))
    os.makedirs(user_dir, exist_ok=True)

    document = message.document
    file_path = os.path.join(user_dir, f"{uuid4()}_{document.file_name}")

    file_info = await bot.get_file(document.file_id)
    file_data = await bot.download_file(file_info.file_path)

    async with aiofiles.open(file_path, mode="wb") as f:
        await f.write(file_data.read())

    await message.reply(f"Файл успешно добавлен!")

@router.message(F.content_type == ContentType.PHOTO)
async def save_photo(message: Message):
    user_id = message.from_user.id
    user_dir = os.path.join(BASE_PATH, str(user_id))
    result_folder = os.path.join(RESULTS_PATH, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    os.makedirs(result_folder, exist_ok=True)

    photo = message.photo[-1]
    file_path = os.path.join(user_dir, f"{uuid4()}_{photo.file_id}.jpg")

    file_info = await bot.get_file(photo.file_id)
    file_data = await bot.download_file(file_info.file_path)

    async with aiofiles.open(file_path, mode="wb") as f:
        await f.write(file_data.read())

    await message.reply(f"Фото успешно добавлено!")

async def convert_to_pdf(in_dir: str, out_file: str):
    """Конвертация изображений в PDF."""
    KNOWN_EXTS = ('.jpg', '.jpeg', '.png')
    images = []
    entries = os.listdir(in_dir)

    for entry in entries:
        _, ext = os.path.splitext(entry)
        if ext.lower() not in KNOWN_EXTS:
            continue
        path_name = os.path.join(in_dir, entry)
        img = Image.open(path_name)
        if img.mode == 'RGBA':
            img = img.convert('RGB')
        images.append(img)

    if images:
        first_frame = images[0]
        first_frame.save(
            out_file,
            save_all=True,
            append_images=images[1:],
            format='PDF'
        )
        [image.close() for image in images]
        return out_file
    else:
        return None

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
