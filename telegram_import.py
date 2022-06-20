import argparse
import configparser
import json
import math
import mimetypes
import os
import pandas
import pandas as pd
import pathlib
import tempfile
import sys
from dateutil.parser import parse
from telethon import functions, types
from telethon.sync import TelegramClient
from tqdm import tqdm


# Telegram does not understand fits own export format - but you can import the Whatsapp one...
# https://github.com/TelegramTools/TLImporter/issues/10
# DD/MM/YY, HH:mm - SenderName SenderSurname: attachment.ext (attached file)\n Chat text or file caption
def convert_to_whatsapp_format(data, only_first_n_messages=math.inf):
    df = pandas.DataFrame.from_dict(data["messages"]).sort_values(by=["date"])
    if math.isfinite(only_first_n_messages):
        df = df[:only_first_n_messages]
    filelist = dict()
    messages = list()
    for index, row in df.iterrows():
        is_photo = False
        file = None
        if ("file" in row.index) and (not pd.isnull(row["file"])):
            file = row["file"]
        else:
            if ("photo" in row.index) and (not pd.isnull(row["photo"])):
                file = row["photo"]
                is_photo = True
            else:
                if ("contact_vcard" in row.index) and (not pd.isnull(row["contact_vcard"])):
                    file = row["contact_vcard"]

        date = parse(row["date"])
        sender = row["from"]

        text = row["text"]
        media_type = row["media_type"]
        if media_type == "sticker":
            if not pd.isnull(row["sticker_emoji"]):
                text = row["sticker_emoji"]
            else:
                text = row["text"]

        if isinstance(text, list):
            tmp_text = ""
            for li in text:
                if isinstance(li, dict):
                    tmp_text += li["text"]
                else:
                    tmp_text += li
            text = tmp_text

        message = "{datetime} - {sender}: ".format(datetime=date.strftime("%d/%m/%y, %H:%M:%S"), sender=sender)
        if file is not None:
            filename = os.path.basename(file)
            filelist[file] = {
                "filename": filename,
                "media_type": media_type,
                "is_photo": is_photo
            }
            if "duration_seconds" in row.index:
                filelist[file]["duration_seconds"] = row["duration_seconds"]
            if "width" in row.index:
                filelist[file]["width"] = row["width"]
            if "height" in row.index:
                filelist[file]["height"] = row["height"]
            message += "{filename} (file attached)\n".format(filename=filename)

        message += text
        if not message.endswith("\n"):
            message += "\n"
        messages.append(message)

    return messages, filelist


def upload_file(client, peer, history_import_id, path, file, file_data):
    file = path + "\\" + file.replace("/", "\\")
    file_name = file_data["filename"]
    media_type = file_data["media_type"]

    try:
        input_file = client.upload_file(file)
    except Exception as e:
        print(e)
        sys.exit(1)

    # these extensions and mimetypes logic is based on original Telegram client for Android
    ext = pathlib.Path(file_name).suffix
    if ext == "":
        ext = ".txt"
    if ext == ".vcard":
        ext = ".vcf"

    mime_type = None
    if ext in mimetypes.types_map:
        mime_type = mimetypes.types_map[ext]
    if mime_type is None:
        if ".opus" == ext:
            mime_type = "audio/opus"
        else:
            if ".webp" == ext:
                mime_type = "image/webp"
            else:
                mime_type = "text/plain"

    w = None
    h = None
    duration = None
    if ("width" in file_data) and (not pd.isnull(file_data["width"])):
        w = int(file_data["width"])
    if ("height" in file_data) and (not pd.isnull(file_data["height"])):
        h = int(file_data["height"])
    if ("duration_seconds" in file_data) and (not pd.isnull(file_data["duration_seconds"])):
        duration = int(file_data["duration_seconds"])
    if (mime_type == "image/jpg") or (mime_type == "image/jpeg"):
        if file_data["is_photo"]:
            media = types.InputMediaUploadedPhoto(file=input_file)
        else:
            attributes = [types.DocumentAttributeImageSize(w, h)]
            media = types.InputMediaUploadedDocument(file=input_file, mime_type=mime_type,
                                                     attributes=attributes)
    else:
        attributes = list()
        if media_type == "animation":
            attributes.append(types.DocumentAttributeAnimated())

        if media_type == "video_file":
            attributes.append(types.DocumentAttributeVideo(duration, w, h))

        if media_type == "sticker":
            attributes.append(types.DocumentAttributeSticker("", types.InputStickerSetEmpty()))
            attributes.append(types.DocumentAttributeImageSize(w, h))

        if media_type == "audio_file":
            attributes.append(types.DocumentAttributeAudio(duration))

        if len(attributes) == 0:
            attributes.append(types.DocumentAttributeFilename(file_name=file_name))

        media = types.InputMediaUploadedDocument(file=input_file, mime_type=mime_type, attributes=attributes)

    try:
        client(functions.messages.UploadImportedMediaRequest(
            peer=peer,
            import_id=history_import_id,
            file_name=file_name,
            media=media
        ))
    except Exception as e:
        print(e)
        sys.exit(2)


def import_history(path, peer, test_only=False, only_first_n_messages=math.inf):
    print("Loading config.ini")
    config = configparser.ConfigParser()
    config.read('config.ini')

    api_id = int(config['API']['api_id'])
    api_hash = config['API']['api_hash']

    print("Loading result.json")
    file = path + r"\result.json"
    with open(file, encoding='utf-8') as f:
        data = json.load(f)
        assert data['type'] == 'personal_chat'

    print("Converting format")
    messages, file_list = convert_to_whatsapp_format(data, only_first_n_messages)
    messages_head = "\n".join(messages[:100])

    with TelegramClient("telegram_import", api_id, api_hash) as client:
        # check if Telegram API understands the import file based on first 100 rows
        (functions.messages.CheckHistoryImportRequest(
            import_head=messages_head
        ))

        # check if the peer is OK for import
        client(functions.messages.CheckHistoryImportPeerRequest(
            peer=peer
        ))

        # create temporary file to store actual messages
        ntf = tempfile.NamedTemporaryFile(mode='w+t', delete=False, encoding='utf-8', prefix="_chat", suffix='.txt')
        ntf.writelines(messages)
        ntf.close()

        # initiate actual import
        print("Staring import")
        history_import = client(functions.messages.InitHistoryImportRequest(
            peer=peer,
            file=client.upload_file(ntf.name),
            media_count=len(file_list)
        ))

        os.remove(ntf.name)

        # upload being mentioned in messages
        print("Upload files mentioned in messages")

        pbar = tqdm(file_list)
        for f in pbar:
            file_data = file_list[f]
            pbar.set_description("Uploading {filename}".format(filename=file_data["filename"]))
            upload_file(client, peer, history_import.id, path, f, file_data)

        if test_only:
            print("Test run complete")
            return

        # messages are there and all the files they are mentioning, so we can now complete the actual import process
        client(functions.messages.StartHistoryImportRequest(
            peer=peer,
            import_id=history_import.id
        ))
        print("Import complete")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog="telegram_import", description="import back messages exported from "
                                                                         "Telegram into JSON format")
    parser.add_argument("--path", required=True, help="path to exported folder")
    parser.add_argument("--peer", required=True, help="peer that we're importing chat with")
    parser.add_argument(
        "--test_only",
        action='store_true',
        help="simulate import, but just don't actually commit it")
    args = parser.parse_args()

    import_history(
        path=args.path,
        peer=args.peer,
        test_only=args.test_only
    )
