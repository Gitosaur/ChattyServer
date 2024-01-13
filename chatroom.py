import asyncio
import uuid


class ChatroomClient:
    def __init__(self, websocket):
        self.id = uuid.uuid4()
        self.habbo_name = ""
        self.mission = ""
        self.figure = ""
        self.sex = ""
        self.hotel = ""
        self._websocket = websocket
        self._queue = asyncio.Queue()
        self._relay_task = asyncio.create_task(self._relay())
        self.rooms = set()

    async def _relay(self):
        while True:
            # Implement custom logic based on queue.qsize() and
            # websocket.transport.get_write_buffer_size() here.
            message = await self._queue.get()
            await self._websocket.send(message)

    def remove(self):
        for room in self.rooms:
            try:
                room.clients.remove(self)
                self.rooms.remove(room)
            except KeyError:
                pass

        self._relay_task.cancel()

    def add_room(self, room):
        try:
            self.rooms.add(room)
        except KeyError:
            pass

    def remove_room(self, room):
        self.rooms.remove(room)

    def send(self, message):
        self._queue.put_nowait(message)

    def set_habbo_name(self, name):
        self.habbo_name = name


class Chatroom:
    def __init__(self, name: str, host: ChatroomClient, password=None):
        self.name = name
        self.clients = set()
        self.password = password
        self.host = host

    def size(self):
        return len(self.clients)

    def add_client(self, client: ChatroomClient):
        try:
            self.clients.add(client)
            client.add_room(self)
        except KeyError:
            pass

    def remove_client(self, client: ChatroomClient):
        try:
            self.clients.remove(client)
            client.remove_room(self)
        except KeyError:
            pass

    def broadcast(self, message):
        for client in self.clients:
            # print(f"[{self.name}] -> {client.id}: {message}")
            client.send(message)

    def get_clients(self):
        return self.clients

    def get_users(self):
        return [{"name": c.habbo_name, "mission": c.mission, "figure": c.figure, "sex": c.sex, "hotel": c.hotel} for c in self.clients]

    def __str__(self):
        return f"[{self.name}] ({', '.join([c.habbo_name for c in self.clients])})"
