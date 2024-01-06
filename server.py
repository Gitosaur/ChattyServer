import asyncio
import json

import websockets

from chatroom import ChatroomClient, Chatroom


class GMServer:
    def __init__(self):
        self._rooms = {
            'sys': Chatroom('sys'),
            't1': Chatroom('t1'),
        }
        print("SERVER START")
        self._clients = []

    def start(self):
        asyncio.run(self._start())

    async def _start(self):
        async with websockets.serve(self._handler, host="0.0.0.0", port=8000):
            # await asyncio.Future()
            await self._broadcast_messages()  # runs forever

    async def _handler(self, websocket):
        client = ChatroomClient(websocket)
        await asyncio.gather(websocket.wait_closed(), self._message_handler(websocket, client))

    async def _on_client_connection_closed(self, client: ChatroomClient):
        print(client.id, client.habbo_name, "Disconnected from the server")
        # must be wrapped in list() because removing causes the size to change while iterating
        if client.habbo_name:
            for room_key in list(self._rooms.keys()):
                await self._leave_room(client, room_key, send_to_client=False)
                print(f"REMOVED {client.habbo_name} from {room_key}")

        if client in self._clients:
            self._clients.remove(client)
        client.remove()

    async def _message_handler(self, websocket, client: ChatroomClient):
        print(f"msg handler id {client.id}")
        try:
            async for message_str in websocket:
                await self._parse_message(client, message_str)
        except Exception:
            pass
        finally:
            print("User", client.habbo_name, "disconnecting...")
            asyncio.ensure_future(self._on_client_connection_closed(client))

    async def _parse_message(self, client: ChatroomClient, message_str):
        try:
            msg = json.loads(message_str)
        except Exception:
            print(f"Error while parsing message {message_str}")
            return

        print(f"recv: {client.id} {msg}")

        if msg['type'] == "connect":
            await self._on_client_connect(client, msg)
        elif msg['type'] == "user_move":
            await self._on_user_move(client, msg)
        elif msg['type'] == "create_room":
            await self._on_room_create(client, msg)
        elif msg['type'] == "join_room":
            await self._on_join_room(client, msg)
        elif msg['type'] == "leave_room":
            await self._on_leave_room(client, msg)
        elif msg['type'] == "room_users":
            await self._on_room_users(client, msg)
        elif msg['type'] == "show_rooms":
            await self._send_rooms_to_client(client)
        elif msg['type'] == "message":
            await self._on_chat_message(client, msg)
        elif msg['type'] == "password":
            await self._on_room_pw_request(client, msg)

    async def _on_client_connect(self, client, msg):
        client.habbo_name = msg['data']['name']
        client.mission = msg['data']['mission']
        client.figure = msg['data']['figure']
        client.sex = msg['data']['sex']
        client.hotel = msg['data']['hotel']

        #check if client is already connected
        for o in self._clients:
            if o.habbo_name == client.habbo_name and o.hotel == client.hotel:
                err_msg = {
                    "type": "connect",
                    "data": {
                        "status": "error",
                        "message": "This user is already connected"
                    }
                }
                client.send(json.dumps(err_msg))
                client.remove()
                return

        msg = {
            "type": "connect",
            "data": {
                "status": "success"
            }
        }
        self._clients.append(client)
        client.send(json.dumps(msg))

    async def _on_user_move(self, client, msg):
        for room in list(client.rooms):
            msg['data']['name'] = client.habbo_name
            msg['data']['hotel'] = client.hotel
            msg['data']['room'] = room.name
            self.broadcast(json.dumps(msg), room.name)

    async def _on_room_create(self, client, msg):
        room = msg['data']['room']
        if "password" in msg['data']:
            pwd = msg['data']['password']
            await self._create_room(client, room, pwd)
        else:
            await self._create_room(client, room)

    async def _on_join_room(self, client, msg):
        room = msg['data']['room']

        print(f"Room request for {room} by socket {client.id}")
        pwd = None
        if "password" in msg['data']:
            pwd = msg['data']['password']
        await self._join_room(client, room, password=pwd)

    async def _on_leave_room(self, client, msg):
        room = msg['data']['room']
        print(f"Leave room request for {room} by socket {client.id}")
        await self._leave_room(client, room)

    async def _on_room_users(self, client, msg):
        room = msg['data']['room']
        await self._send_room_users(client, room)

    async def _on_chat_message(self, client, msg):
        msg['data']['hotel'] = client.hotel
        if "room" in msg['data']:
            await self._broadcast_message_to_room(client, msg)
        else:
            await self._broadcast_message(client, msg)

    async def _on_room_pw_request(self, client, msg):
        room = msg["data"]["room"]
        await self._get_room_password(client, room)

    async def _get_room_password(self, client: ChatroomClient, room: str):
        err = {"type": "password_error", "data": {}}
        if room not in self._rooms:
            err['data']['message'] = "The room does not exist"
            client.send(json.dumps(err))
        elif client not in self._rooms[room].clients:
            err['data']['message'] = "You are not member of this room"
            client.send(json.dumps(err))
        else:
            msg = {
                "type": "password",
                "data": {
                    "room": room,
                    "password": self._rooms[room].password or ""
                }
            }
            client.send(json.dumps(msg))

    async def _broadcast_message_to_room(self, client: ChatroomClient, msg):
        room = msg['data']['room']
        err = {"type": "message_error", "data": {}}

        if room not in self._rooms:
            err['data']['message'] = "Room does not exist"
            client.send(json.dumps(err))
        elif client in self._rooms[room].clients:
            msg['data']['habbo'] = client.habbo_name
            self.broadcast(json.dumps(msg), room)
        else:
            err['data']['message'] = "You are not member of this room"
            client.send(json.dumps(err))

    async def _broadcast_message(self, client: ChatroomClient, message):
        message['data']['habbo'] = client.habbo_name
        for room in client.rooms:
            message['data']['room'] = room.name
            print(message)
            room.broadcast(json.dumps(message))

    async def _send_rooms_to_client(self, client: ChatroomClient):
        msg = {
            "type": "show_rooms",
            "data": {
                "rooms": [{"name": name,
                           "password": True if room.password else False,
                           "users": room.get_users()
                           } for name, room in self._rooms.items()]
            }
        }
        client.send(json.dumps(msg))

    async def _send_room_users(self, client: ChatroomClient, room: str):
        if room in self._rooms:
            msg = {
                "type": "room_users",
                "data": {
                    "room": room,
                    "users": self._rooms[room].get_users()
                }
            }
            client.send(json.dumps(msg))
        else:
            err = {
                "type": "room_users_error",
                "data": {
                    "room": room,
                    "message": "The room does not exist"
                }
            }
            client.send(json.dumps(err))

    async def _create_room(self, client: ChatroomClient, room_name: str, password=None):
        err = {"type": "create_room_error", "data": {}}
        if not room_name:
            err['data']['message'] = "The room name must not be empty"
            client.send(json.dumps(err))
        elif room_name in self._rooms:
            err['data']['message'] = "The room you want to create already exists"
            client.send(json.dumps(err))
        else:
            self._rooms[room_name] = Chatroom(room_name, password)
            await self._join_room(client, room_name, password)
            for c in self._clients:
                creator = {
                    "name": client.habbo_name,
                    "figure": client.figure,
                    "mission": client.mission,
                    "sex": client.sex,
                    "hotel": client.hotel
                }
                c.send(json.dumps({
                    "type": "new_room",
                    "data": {
                        "name": room_name,
                        "password": True if password else False,
                        "creator": creator
                    }
                }))

    async def _join_room(self, client: ChatroomClient, room_name: str, password=None):
        err = {
            "type": "join_room_error",
            "data": {
                "room": room_name,
            }
        }

        if room_name not in self._rooms.keys():
            err['data']['message'] = "The room you want to join does not exist"
            client.send(json.dumps(err))
        elif client in self._rooms[room_name].clients:
            err['data']['message'] = f"You are already member of {room_name}"
            client.send(json.dumps(err))
        else:
            # check if room is password protected
            room = self._rooms[room_name]
            if room.password is not None:
                if password is None:
                    err['data']['message'] = "You must provide a password to join this room"
                    client.send(json.dumps(err))
                    return
                elif room.password != password:
                    err['data']['message'] = "Wrong password"
                    client.send(json.dumps(err))
                    return

            print(f"Adding client {client.habbo_name} ({client.id}) to room {room.name}")
            room.add_client(client)

            #send the client a list of all users in the room:
            user_list_msg = {
                "type": "room_info",
                "data": {
                    "room": room_name
                }
            }
            room_user_list = []
            for c in room.clients:
                room_user_list.append({
                    "name": c.habbo_name,
                    "figure": c.figure,
                    "mission": c.mission,
                    "sex": c.sex,
                    "hotel": c.hotel
                })

            user_list_msg["data"]["users"] = room_user_list
            client.send(json.dumps(user_list_msg))

            # notify all users that a new user joined
            user_joined_msg = {
                "type": "user_joined",
                "data": {
                    "room": room_name,
                    "name": client.habbo_name,
                    "mission": client.mission,
                    "figure": client.figure,
                    "sex": client.sex,
                    "hotel": client.hotel
                }
            }
            for other in self._clients:
                other.send(json.dumps(user_joined_msg))

    async def _leave_room(self, client: ChatroomClient, room: str, send_to_client=True):
        if room not in self._rooms.keys():
            err = {
                "type": "leave_room_error",
                "data": {
                    "room": room,
                    "message": "The room you want to leave does not exist"
                }
            }
            if send_to_client:
                client.send(json.dumps(err))
        elif client not in self._rooms[room].clients:
            err = {
                "type": "leave_room_error",
                "data": {
                    "room": room,
                    "message": "You are not member of the room you want to leave"
                }
            }
            if send_to_client:
                client.send(json.dumps(err))
        else:
            print(f"Removing client {client.id} from room {self._rooms[room].name}")
            # self.broadcast(f"Removing client {client.id} from room {self._rooms[room].name}", 'sys')
            self._rooms[room].remove_client(client)

            # delete room if empty
            if self._rooms[room].size() == 0:
                del self._rooms[room]

            msg = {
                "type": "user_left",
                "data": {
                    "room": room,
                    "name": client.habbo_name,
                    "hotel": client.hotel
                }
            }
            # notify group members that habbo left
            # self.broadcast(json.dumps(msg), room)
            for other in self._clients:
                if client != other:
                    other.send(json.dumps(msg))

            # notify the habbo that he successfully left
            if send_to_client:
                client.send(json.dumps(msg))

    def broadcast(self, message, room):
        if room in self._rooms:
            self._rooms[room].broadcast(message)

    async def _broadcast_messages(self):
        while True:
            await asyncio.sleep(7)
            self.broadcast("BROADCAST TEST", 'broadcast')
        #   for r in self._rooms:
        #       print(self._rooms[r])


if __name__ == "__main__":
    server = GMServer()
    print(server)
    server.start()

