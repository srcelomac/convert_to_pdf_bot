import os
import shutil
from aiogram import Bot, Router, F
from aiogram.filters import Command
from aiogram.types import Message, InputFile
from aiogram.fsm.context import FSMContext
import asyncio
from aiogram import Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
from pathlib import Path
from PIL import Image
from PyPDF2 import PdfMerger
from typing import List, Tuple

# Загрузка токена из .env
env_path = Path("venv") / ".env"
load_dotenv(dotenv_path='.env')

TG_TOKEN = os.getenv('TG_TOKEN')

bot = Bot(token=TG_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()

# Папка для хранения файлов
BASE_PATH = "user_files"
RESULTS_PATH = "results"


# Команда /start
@router.message(Command(commands=["start"]))
async def send_welcome(message: types.Message):
    await message.answer(
        "Привет! Я бот для обработки файлов. Отправьте файл для обработки."
    )


# Команда /help
@router.message(Command(commands=["help"]))
async def send_help(message: types.Message):
    await message.answer(
        "Я могу принимать и обрабатывать файлы. Просто отправьте файл или фото, и я обработаю их для вас."
    )


# Обработка всех типов файлов (фото, документы)
@router.message(F.document | F.photo | F.video)
async def new_func(message: types.Message):
    user_id = message.from_user.id
    user_folder = os.path.join(BASE_PATH, str(user_id))

    # Создание папки для пользователя, если её нет
    if not os.path.exists(user_folder):
        os.makedirs(user_folder)

    # Собираем все файлы в одном сообщении
    file_paths = []

    # Проверяем, если есть документы
    if message.document:
        file = message.document
        file_id = file.file_id
        file_name = file.file_name

        file = await bot.get_file(file_id)
        file_path = file.file_path
        local_file_path = os.path.join(user_folder, file_name)
        await bot.download_file(file_path, local_file_path)

        file_paths.append(local_file_path)

    # Проверяем, если есть фотографии
    if message.photo:
        for file in message.photo:
            file_id = file.file_id
            file_name = f"{user_id}_photo.jpg"  # Генерируем имя для каждого фото

            file = await bot.get_file(file_id)
            file_path = file.file_path
            local_file_path = os.path.join(user_folder, file_name)
            await bot.download_file(file_path, local_file_path)

            file_paths.append(local_file_path)

    # Проверяем, если есть видео
    if message.video:
        file = message.video
        file_id = file.file_id
        file_name = f"{user_id}_video.mp4"

        file = await bot.get_file(file_id)
        file_path = file.file_path
        local_file_path = os.path.join(user_folder, file_name)
        await bot.download_file(file_path, local_file_path)

        file_paths.append(local_file_path)

    # После того как все файлы скачаны, объединяем их в один итоговый файл
    # Путь для сохранения объединенного файла
    result_folder = os.path.join(RESULTS_PATH, str(user_id))

    # Создаем папку для результатов, если её нет
    if not os.path.exists(result_folder):
        os.makedirs(result_folder)

    # Итоговый путь для PDF файла
    final_pdf_path = os.path.join(result_folder, "processed_result_final.pdf")

    # Выполняем объединение файлов в итоговый PDF
    processed_pdf = await convert_to_pdf(user_folder, final_pdf_path)

    # Отправляем итоговый PDF файл пользователю
    await message.answer("Вот результат вашей обработки:")

    from aiogram.types.input_file import FSInputFile

    doc = FSInputFile(final_pdf_path, filename=f'result.pdf')
    await message.reply_document(doc)

    # Очистим папку пользователя после отправки
    shutil.rmtree(user_folder)


async def convert_to_pdf(in_dir: str, out_file: str):
    """
    Конвертирует изображения и PDF файлы в указанной папке в один PDF файл.
    :param in_dir: Папка с изображениями и PDF файлами
    :param out_file: Путь для сохранения итогового PDF
    :return: Путь к сохраненному PDF файлу
    """
    images: List[Image.Image] = []
    pdf_merger = PdfMerger()  # Объединитель PDF файлов

    # Получаем список всех файлов в папке
    files = os.listdir(in_dir)

    for file_name in files:
        full_path = os.path.join(in_dir, file_name)

        # Если это изображение
        if file_name.lower().endswith(('jpg', 'jpeg', 'png', 'bmp', 'gif')):
            try:
                img = Image.open(full_path)
                if img.mode == 'RGBA':
                    img = img.convert('RGB')  # Конвертируем в RGB, чтобы убрать альфа-канал
                images.append(img)
            except:
                print(f"Не удалось обработать файл {full_path}, так как это не изображение.")

        # Если это PDF файл
        elif file_name.lower().endswith('.pdf'):
            try:
                pdf_merger.append(full_path)
            except Exception as e:
                print(f"Не удалось обработать PDF файл {full_path}: {e}")

    # Если есть изображения, конвертируем их в PDF
    if images:
        first_frame = images[0]
        first_frame.save(
            out_file,
            save_all=True,
            append_images=images[1:],  # Добавляем остальные изображения
            format='PDF',
        )

    # Если были PDF файлы, объединяем их с изображениями
    if os.path.exists(out_file) and pdf_merger.pages:
        pdf_merger.append(out_file)  # Добавляем сгенерированный PDF
        final_pdf_path = out_file.replace('.pdf', '_final.pdf')
        pdf_merger.write(final_pdf_path)
        return final_pdf_path
    elif images:
        return out_file
    else:
        return out_file  # Возвращаем путь, даже если ничего не было обработано


async def main():
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
