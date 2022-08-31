from http import cookies
import os
import json
from typing import Tuple
from time import time
from dataclasses import dataclass
import string
import random
from urllib import response
from httpx import Timeout, Limits, HTTPTransport, Client

from nyan.util import Serializable


@dataclass
class IssueConfig:
    name: str
    channel_id: int
    discussion_id: int
    bot_token: str
    hg_channel_id: int = 0
    last_update_id: int = 0

@dataclass
class MessageId(Serializable):
    message_id: int
    issue: str = "main"
    from_discussion: bool = False

    def as_tuple(self):
        return (self.issue, self.message_id)

    def __hash__(self):
        return hash(self.as_tuple())

    def __eq__(self, another):
        return self.as_tuple() == another.self.as_tuple()


class HGClient:
    def __init__(self, config_path):
        assert os.path.exists(config_path)
        with open(config_path) as r:
            self.config = json.load(r)

        timeout = Timeout(
            connect=self.config.get("connect_timeout", 10.0),
            read=self.config.get("read_timeout", 10.0),
            write=self.config.get("write_timeout", 10.0),
            pool=self.config.get("pool_timeout", 1.0),
        )
        limits = Limits(
            max_connections=self.config.get("connection_pool_size", 1),
            max_keepalive_connections=self.config.get("connection_pool_size", 1),
        )
        transport = HTTPTransport(
            retries=self.config.get("retries", 5)
        )
        self.client = Client(
            timeout=timeout,
            limits=limits,
            transport=transport
        )

        self.cookies = {}

        # Print config self.config["issues"]
        print('Issues:')
        print(self.config["issues"])

        self.issues = {config["name"]: IssueConfig(**config) for config in self.config["issues"]}
        self.login(self.config.get('hg_login'), self.config.get('hg_password'))

    def login(self, login, password):
        # Login and save cookies
        # get csrf token
        response = self.client.get("https://hongkong.zoibana.ru/login")
        csrf_token = response.text.split("name=\"_token\" value=\"")[1].split("\"")[0]
        # login
        params = {
            "email": login,
            "password": password,
            "_token": csrf_token,
        }
        response = self.client.post("https://hongkong.zoibana.ru/login", params=params)
        if response.status_code != 302:
            raise Exception("Login failed")
        self.cookies = response.cookies

    def getCSRF(self):
        # open https://hongkong.zoibana.ru/new
        response = self.client.get("https://hongkong.zoibana.ru/new")
        # get csrf token
        # window.Laravel = {csrfToken: 'IzmbvfNIFTSXhLcmoJTIk4BDdBuerb9DzcvKhlpj'};
        csrf_token = response.text.split("csrfToken: '")[1].split("'")[0]
        return csrf_token

    def send_message(
        self,
        text: str,
        issue_name: str,
        photos: Tuple[str] = tuple()
    ):
        print(f"Sending message to {issue_name}")
        issue = self.issues[issue_name]
        # Print channel id
        print(f"Channel id: {issue.hg_channel_id}")

        # Stay only tech news
        if issue.hg_channel_id == 0:
           return None
        
        response = None
        if len(photos):
            response = self._send_photo(text, photos[0], issue=issue)
        else:
            response = self._send_text(text, issue=issue)

        print("Send status code:", response.status_code)
        if response.status_code != 200:
            print("Send error:", response.text)
            return None

        return True


    def _send_text(self, text, issue, photo_url=None):
        timestamp_ms = int(round(time() * 1000))
        # Get random text ID like tQz3N9odLw, 10 symbol [a-zA-Z0-9]
        randomBlockId = "".join(
            [random.choice(string.ascii_letters + string.digits) for n in range(10)]
        )


        params = {
            "header": "",
            "channel_id": issue.hg_channel_id,
            "body":{
                "time": timestamp_ms,
                "blocks":
                    [
                        {"id":randomBlockId,"type":"paragraph","data":{"text":text}},
                    ],
                "version":"2.25.0"
            }
        }

        headers = {
            'x-csrf-token': self.getCSRF(),
        }

        if photo_url:
            randomBlockId2 = "".join(
                [random.choice(string.ascii_letters + string.digits) for n in range(10)]
            )
	        # If has photo, add it to body after text

            params["body"]["blocks"].append({"id":randomBlockId2,"type":"image","data":{"file":{"url":photo_url},"caption": "","withBorder":True,"stretched":True,"withBackground":False}})

        # Send body as json
        return self.client.post("https://hongkong.zoibana.ru/api/v1.1/posts", json=params, cookies=self.cookies, headers=headers)

    def _send_photo(self, text, photo, issue):
        # Example response: {file: {url: "https://hongkong.zoibana.ru/images/ca013e09381381b6ed829d89ce24a251.png",} success: true}
        # Image field: image
        # Download photo by url and save to tmp file
        
        # Create tmp file
        tmp_file = os.path.join(os.path.dirname(__file__), "tmp.jpg")
        with open(tmp_file, "wb") as f:
            f.write(self.client.get(photo).content)
        # Upload photo
        
        # content-type: multipart/form-data;
        files = {'image': open(tmp_file, 'rb')}
        headers = {
            'x-csrf-token': self.getCSRF(),
        }
        req = self.client.post("https://hongkong.zoibana.ru/image/upload", files=files, cookies=self.cookies, headers=headers)
        os.remove(tmp_file)
        if req.status_code != 200:
            print("Upload error:", req.text)
            return None
        result = req.json()
        print("Upload result:", result)
        if not result["success"]:
            print("Upload error:", result["error"])
            return None
        photo_url = result['file']["url"]

        return self._send_text(text, issue=issue, photo_url=photo_url)

    def _post(self, url, params):
	    # use cookies
        return self.client.post(url, params=params, cookies=self.cookies)
        # return self.client.post(url, data=params)
