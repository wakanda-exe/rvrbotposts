import asyncio
import logging
from io import BytesIO
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, InputMediaVideo

# Логирование
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

TOKEN = "8351981749:AAGS2WofVPr1_kNMQ_asGuIqCaIS4KjpTs0"
CHANNEL_ID = -1003438380699  # ID канала
CHANNEL_LINK = "https://t.me/rvaitech"

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Хранилище для медиагрупп
media_groups = {}
media_group_timers = {}
media_group_sent_messages = {}  # Храним ID отправленных медиагрупп
single_message_data = {}  # Храним данные одиночных сообщений

def utf16_len(text: str) -> int:
    """Возвращает длину строки в UTF-16 code units"""
    return len(text.encode('utf-16-le')) // 2

async def process_text(text: str, entities: list = None, max_length: int = None) -> tuple:
    """
    Обрабатываем текст:
    - Если последняя строка содержит ссылку - заменяем на @rvaitech
    - Если последняя строка обычный текст - добавляем пустую строку и @rvaitech
    Возвращаем (новый_текст, новые_entities)
    """
    replacement_text = "@rvaitech"
    
    if not text:
        entities_list = [
            types.MessageEntity(type="bold", offset=0, length=len(replacement_text))
        ]
        return replacement_text, entities_list
    
    lines = text.split('\n')
    
    # Проверяем, содержит ли последняя строка ссылку
    last_line_has_link = False
    if entities and len(lines) > 0:
        # Находим позицию начала последней строки
        if len(lines) > 1:
            text_before_last = '\n'.join(lines[:-1]) + '\n'
            last_line_start = len(text_before_last)
        else:
            last_line_start = 0
        
        # Проверяем entities в последней строке
        for entity in entities:
            if entity.offset >= last_line_start:
                # Entity находится в последней строке
                if entity.type in ['url', 'text_link', 'mention', 'text_mention']:
                    last_line_has_link = True
                    break
    
    # Обрабатываем текст
    if last_line_has_link:
        # Заменяем последнюю строку
        if len(lines) > 1:
            lines[-1] = replacement_text
        else:
            lines = [replacement_text]
    else:
        # Добавляем через пустую строку
        lines.append("")  # Пустая строка
        lines.append(replacement_text)
    
    new_text = '\n'.join(lines)
    
    # Если текст слишком длинный - обрезаем
    if max_length and len(new_text) > max_length:
        available = max_length - len(f"\n...\n\n{replacement_text}")
        if available > 0:
            truncated = new_text[:available]
            last_newline = truncated.rfind('\n')
            if last_newline > 0:
                truncated = truncated[:last_newline]
            new_text = f"{truncated}\n...\n\n{replacement_text}"
        else:
            new_text = replacement_text
    
    # Пересчитываем позицию @rvaitech в финальном тексте
    lines = new_text.split('\n')
    if len(lines) > 1:
        text_before_last = '\n'.join(lines[:-1]) + '\n'
        last_line_start_utf16 = utf16_len(text_before_last)
    else:
        last_line_start_utf16 = 0
    
    # Копируем entities, исключая те, что после нашей подписи
    new_entities = []
    if entities:
        for entity in entities:
            if entity.offset < last_line_start_utf16:
                if entity.offset + entity.length > last_line_start_utf16:
                    # Entity заходит в нашу подпись - обрезаем
                    new_length = last_line_start_utf16 - entity.offset
                    if new_length > 0:
                        new_entity = types.MessageEntity(
                            type=entity.type,
                            offset=entity.offset,
                            length=new_length,
                            url=entity.url if hasattr(entity, 'url') else None,
                            user=entity.user if hasattr(entity, 'user') else None,
                            language=entity.language if hasattr(entity, 'language') else None,
                            custom_emoji_id=entity.custom_emoji_id if hasattr(entity, 'custom_emoji_id') else None
                        )
                        new_entities.append(new_entity)
                else:
                    new_entities.append(entity)
    
    # Добавляем жирное форматирование для @rvaitech
    text_length_utf16 = utf16_len(replacement_text)
    
    bold_entity = types.MessageEntity(
        type="bold",
        offset=last_line_start_utf16,
        length=text_length_utf16
    )
    new_entities.append(bold_entity)
    
    return new_text, new_entities if new_entities else None

async def download_file_to_bytes(file_id: str) -> BytesIO:
    """Скачиваем файл в память и возвращаем BytesIO."""
    file = await bot.get_file(file_id)
    buffer = BytesIO()
    await bot.download_file(file.file_path, buffer)
    buffer.seek(0)
    return buffer

@dp.callback_query(F.data.startswith("send_single:"))
async def send_single_to_channel_callback(callback: types.CallbackQuery):
    """Обработчик нажатия на кнопку 'Отправить в канал' для одиночных медиа"""
    try:
        message_id = int(callback.data.split(":", 1)[1])
        
        if message_id not in single_message_data:
            await callback.answer("❌ Сообщение не найдено", show_alert=True)
            return
        
        msg_data = single_message_data[message_id]
        
        # Отправляем в канал отредактированное сообщение
        if msg_data['type'] == 'photo':
            await bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=msg_data['file_id'],
                caption=msg_data['caption'],
                caption_entities=msg_data['caption_entities']
            )
        elif msg_data['type'] == 'video':
            await bot.send_video(
                chat_id=CHANNEL_ID,
                video=msg_data['file_id'],
                caption=msg_data['caption'],
                caption_entities=msg_data['caption_entities']
            )
        elif msg_data['type'] == 'document':
            await bot.send_document(
                chat_id=CHANNEL_ID,
                document=msg_data['file_id'],
                caption=msg_data['caption'],
                caption_entities=msg_data['caption_entities']
            )
        elif msg_data['type'] == 'text':
            await bot.send_message(
                chat_id=CHANNEL_ID,
                text=msg_data['text'],
                entities=msg_data['entities']
            )
        
        # Уведомляем пользователя
        await callback.answer("✅ Пост успешно отправлен в канал!", show_alert=True)
        
        # Убираем кнопку после отправки
        await callback.message.edit_reply_markup(reply_markup=None)
        
        logger.info(f"Пост отправлен в канал {CHANNEL_ID} пользователем {callback.from_user.full_name}")
        
        # Очищаем данные
        del single_message_data[message_id]
        
    except Exception as e:
        logger.error(f"Ошибка при отправке в канал: {e}", exc_info=True)
        await callback.answer("❌ Ошибка при отправке в канал", show_alert=True)

@dp.callback_query(F.data.startswith("send_media_group:"))
async def send_media_group_to_channel(callback: types.CallbackQuery):
    """Обработчик нажатия на кнопку для медиагруппы"""
    try:
        media_group_id = callback.data.split(":", 1)[1]
        
        if media_group_id not in media_group_sent_messages:
            await callback.answer("❌ Медиагруппа не найдена", show_alert=True)
            return
        
        group_data = media_group_sent_messages[media_group_id]
        
        # Отправляем медиагруппу в канал
        await bot.send_media_group(
            chat_id=CHANNEL_ID,
            media=group_data['media']
        )
        
        # Уведомляем пользователя
        await callback.answer("✅ Альбом успешно отправлен в канал!", show_alert=True)
        
        # Убираем кнопку
        await callback.message.edit_reply_markup(reply_markup=None)
        
        logger.info(f"Медиагруппа отправлена в канал {CHANNEL_ID} пользователем {callback.from_user.full_name}")
        
        # Очищаем данные
        del media_group_sent_messages[media_group_id]
        
    except Exception as e:
        logger.error(f"Ошибка при отправке медиагруппы в канал: {e}", exc_info=True)
        await callback.answer("❌ Ошибка при отправке", show_alert=True)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Команда /start"""
    await message.answer(
        "👋 Привет! Отправь мне сообщение с текстом (можно с форматированием), "
        "фото, видео или документ - я заменю последнюю строку на **@rvaitech**"
    )

async def process_media_group(user_id: int, media_group_id: str):
    """Обрабатываем собранную медиагруппу"""
    await asyncio.sleep(1)  # Ждём, пока все медиа соберутся
    
    if media_group_id not in media_groups:
        return
    
    messages = media_groups[media_group_id]
    del media_groups[media_group_id]
    
    if media_group_id in media_group_timers:
        del media_group_timers[media_group_id]
    
    # Берём текст из первого сообщения с текстом
    text = None
    entities = None
    for msg in messages:
        if msg.caption:
            text = msg.caption
            entities = msg.caption_entities
            break
    
    # Обрабатываем текст
    new_text, new_entities = await process_text(text, entities, max_length=1024) if text else (None, None)
    
    # Создаём медиа список
    media = []
    for i, msg in enumerate(messages):
        if msg.photo:
            media_item = InputMediaPhoto(
                media=msg.photo[-1].file_id,
                caption=new_text if i == 0 else None,
                caption_entities=new_entities if i == 0 else None
            )
            media.append(media_item)
        elif msg.video:
            media_item = InputMediaVideo(
                media=msg.video.file_id,
                caption=new_text if i == 0 else None,
                caption_entities=new_entities if i == 0 else None
            )
            media.append(media_item)
    
    # Создаём кнопку
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Отправить в канал", callback_data=f"send_media_group:{media_group_id}")]
    ])
    
    try:
        # Отправляем медиагруппу
        sent_messages = await bot.send_media_group(
            chat_id=messages[0].chat.id,
            media=media,
            reply_to_message_id=messages[0].message_id
        )
        
        # Сохраняем информацию о медиагруппе для отправки в канал
        media_group_sent_messages[media_group_id] = {
            'media': media,
            'caption': new_text,
            'caption_entities': new_entities
        }
        
        # Отправляем кнопку под последним медиа в группе
        await bot.send_message(
            chat_id=messages[0].chat.id,
            text="⬆️",  # Стрелка вверх
            reply_to_message_id=sent_messages[-1].message_id,
            reply_markup=keyboard
        )
        
        logger.info(f"Отправлена медиагруппа ({len(media)} медиа)")
        
    except Exception as e:
        logger.error(f"Ошибка при отправке медиагруппы: {e}", exc_info=True)

@dp.message()
async def handle_message(message: types.Message):
    user = message.from_user
    text = message.text or message.caption
    entities = message.entities or message.caption_entities
    
    logger.info(f"Получено сообщение от {user.full_name} ({user.id})")
    
    # Проверяем, является ли это частью медиагруппы
    if message.media_group_id:
        # Это медиагруппа (альбом)
        media_group_id = message.media_group_id
        
        if media_group_id not in media_groups:
            media_groups[media_group_id] = []
        
        media_groups[media_group_id].append(message)
        
        # Отменяем предыдущий таймер, если есть
        if media_group_id in media_group_timers:
            media_group_timers[media_group_id].cancel()
        
        # Создаём новый таймер для обработки группы
        task = asyncio.create_task(process_media_group(user.id, media_group_id))
        media_group_timers[media_group_id] = task
        
        return
    
    # Создаём кнопку "Отправить"
    # keyboard = InlineKeyboardMarkup(inline_keyboard=[
    #     [InlineKeyboardButton(text="📤 Отправить в канал", callback_data=f"send_to_channel")]
    # ])
    
    try:
        # Фото
        if message.photo:
            # Для фото лимит подписи 1024 символа
            new_text, new_entities = await process_text(text, entities, max_length=1024) if text else (None, None)
            
            buffer = await download_file_to_bytes(message.photo[-1].file_id)
            input_file = types.BufferedInputFile(buffer.read(), filename="photo.jpg")
            sent_msg = await message.reply_photo(
                input_file, 
                caption=new_text,
                caption_entities=new_entities,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📤 Отправить в канал", callback_data=f"send_single:{message.message_id}")]
                ])
            )
            
            # Сохраняем данные для отправки в канал
            single_message_data[message.message_id] = {
                'type': 'photo',
                'file_id': message.photo[-1].file_id,
                'caption': new_text,
                'caption_entities': new_entities
            }
            
            logger.info("Отправлено фото с подписью")
        
        # Видео
        elif message.video:
            # Для видео лимит подписи 1024 символа
            new_text, new_entities = await process_text(text, entities, max_length=1024) if text else (None, None)
            
            buffer = await download_file_to_bytes(message.video.file_id)
            input_file = types.BufferedInputFile(buffer.read(), filename="video.mp4")
            sent_msg = await message.reply_video(
                input_file,
                caption=new_text,
                caption_entities=new_entities,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📤 Отправить в канал", callback_data=f"send_single:{message.message_id}")]
                ])
            )
            
            # Сохраняем данные для отправки в канал
            single_message_data[message.message_id] = {
                'type': 'video',
                'file_id': message.video.file_id,
                'caption': new_text,
                'caption_entities': new_entities
            }
            
            logger.info("Отправлено видео с подписью")
        
        # Документ
        elif message.document:
            # Для документа лимит подписи 1024 символа
            new_text, new_entities = await process_text(text, entities, max_length=1024) if text else (None, None)
            
            buffer = await download_file_to_bytes(message.document.file_id)
            fname = message.document.file_name or "file"
            input_file = types.BufferedInputFile(buffer.read(), filename=fname)
            sent_msg = await message.reply_document(
                input_file,
                caption=new_text,
                caption_entities=new_entities,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📤 Отправить в канал", callback_data=f"send_single:{message.message_id}")]
                ])
            )
            
            # Сохраняем данные для отправки в канал
            single_message_data[message.message_id] = {
                'type': 'document',
                'file_id': message.document.file_id,
                'caption': new_text,
                'caption_entities': new_entities
            }
            
            logger.info("Отправлен документ с подписью")
        
        # Только текст
        elif text:
            # Для текста лимит 4096 символов
            new_text, new_entities = await process_text(text, entities, max_length=4096)
            sent_msg = await message.reply(
                new_text, 
                entities=new_entities, 
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📤 Отправить в канал", callback_data=f"send_single:{message.message_id}")]
                ])
            )
            
            # Сохраняем данные для отправки в канал
            single_message_data[message.message_id] = {
                'type': 'text',
                'text': new_text,
                'entities': new_entities
            }
            
            logger.info("Отправлен текст с заменой последней строки")
        
        else:
            await message.reply("Не могу обработать это сообщение 😅")
            logger.warning("Сообщение не содержит текста или поддерживаемого медиа")
            
    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения: {e}", exc_info=True)
        await message.reply("Произошла ошибка при обработке сообщения 😞")

async def main():
    logger.info("Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())