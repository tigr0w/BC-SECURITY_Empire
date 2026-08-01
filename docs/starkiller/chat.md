# Operator Chat

Empire ships a real-time chat channel for operators connected to the same server, exposed in Starkiller. It is intended for ad-hoc coordination during an engagement and is captured in post-engagement reports.

## How it works

* All operators share a single `general` room. Joining the room broadcasts a `<user> has entered the room` notice; leaving broadcasts the equivalent leave notice.
* Sending a message broadcasts it to everyone currently in the room, tagged with the sender's username and a UTC timestamp.
* On join, the **most recent 20 messages** are replayed to the joining operator so they have context.

Chat is delivered over the existing Socket.IO connection used by Starkiller (events `chat/join`, `chat/leave`, `chat/message`, `chat/history`, `chat/participants`). It uses the same JWT auth as the rest of the API — no separate login.

## Persistence

Chat messages are persisted to the `chat_messages` table in the Empire database. They survive server restarts and are retained for the lifetime of the database. There is no automatic retention or pruning today; if you want a clean slate between engagements, reset the database (`./ps-empire server --reset`) along with your other data.

The persisted record stores the sender's `user_id`, a snapshot of the `username` at send time, the message body, and the UTC `created_at` timestamp. The username snapshot means messages from operators who were later renamed or removed still render correctly in reports.

## Downloading the chatlog

The `basic_reporting` plugin exports the full chat history as a CSV.

* Run with `report=chat` to get only the chatlog:
  ```bash
  curl -X POST https://<empire>/api/v2/plugins/basic_reporting/execute \
       -H "Authorization: Bearer <token>" \
       -d '{"options": {"report": "chat"}}'
  ```
* Run with `report=all` to bundle the chatlog alongside `sessions.csv`, `credentials.csv`, and `master.log`.

The output file `chatlog.csv` has columns `Timestamp,Username,Message`, sorted oldest-first. Download it via the URL returned in the plugin task's `downloads` field (or browse to `Downloads` in Starkiller). Each plugin run produces fresh files; running the report multiple times will create `chatlog.csv`, `chatlog(1).csv`, etc.
