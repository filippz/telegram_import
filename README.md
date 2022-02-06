# telegram_import
Imports the messages exported to JSON format from Telegram back into it.
It converts exported JSON to the WhatsApp format to trick the Telegram API to accept the import.

### Getting started

Simply clone/download this repository, copy/rename `config_template.ini` to `config.ini` and fill the `api_id` and 
`api_hash` with appropriate values (get them here: [Telegram Apps](https://my.telegram.org/apps)). 

### Dependencies

Dependencies for your python environment are listed in `requirements.txt` - install them with: 

`pip install -r requirements.txt`

## Usage

```
python3 telegram_import.py --path <path_to_exported_folder> --peer <chat_peer_phone_number> [--test_only]
```

#### Usage example

```
python3 telegram_import.py --path "C:\Users\filip\Downloads\Telegram Desktop\ChatExport_2022-02-05" --peer
"+123456789"
```

## Notes
If your peer deletes the chat history on his side (without selecting "Also delete for..."), you can export the data from
your side. Unfortunately, there is no way for your peer to import the exported data back without using something like
this.

Imported data is seen on both sides (so you essentially have double messages - the original and imported ones on
your side). Imported messages are visibly flagged as such, and have the date/time of import and visible original
date/time.