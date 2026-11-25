# Knowledge bases

A knowledge base is a set of your own documents that agents can search to answer questions.

## Create one

Open the [Library](#library), choose **Add**, then **Knowledge base**, or go straight to [a new knowledge base](#library/knowledge/~new). Enter a **Name** and, if you like, a **Description**, then choose **Create**. A name over 43 characters is fine, but the agent's search tool gets a shortened name.

## Add your documents

Open the knowledge base and find the **Folders** section. Type the full path of a folder under **Folder path** and choose **Add folder**. The app reads the folder with your own permissions, so register only folders you want agents to search. It can't register the app's own data folder.

The app then reads the folder in the background and indexes the files in it. It keeps the index current: it watches the folder for changes, and it also re-checks every few minutes. Indexing carries on where it left off if the app is restarted.

The app indexes text-based files, such as plain text, Markdown, source code, and data files like CSV and JSON. Other formats, such as PDFs and Office documents, aren't indexed yet.

Removing a folder removes every file indexed from it, along with its search entries. Your files on disk aren't touched.

## Check on it

- Each folder shows its **status** and whether it is being watched, and lists its files. A file's menu offers **View chunks** and **View source**, so you can see how it was split up and what text was read.
- The **Status** section counts files that are pending, indexing, indexed or failed. **Re-index changed files** re-checks every folder and indexes only what differs. **Re-index all files** starts again from scratch for every file.
- **Search** lets you try a query against the knowledge base yourself, the way an agent would.
- Files added one at a time, not from a folder, appear under **Individual files**. They aren't watched, so use **Re-index all files** after editing them.

## Give an agent the knowledge

A knowledge base does nothing until you attach it. Open [Agents](#agents), pick an agent, open its **Knowledge** tab, and turn on the knowledge base. The agent gets a search tool for it, and the row shows the tool's name. An agent can search only what you attach.

Searches combine meaning-based and keyword matching, so a question phrased differently from the document still finds it, and an exact term such as an identifier is found too. If one kind of search is unavailable, the agent is told, and the other is used.

## Indexing settings

[Knowledge indexing](#settings/knowledge-indexing) in Settings sets the chunk size, the chunk overlap, how often folders are re-checked and whether folders are watched. Chunk changes apply to files indexed from then on. The embedding model and the vector store are fixed by the app and shown for reference.

## Ask GleepGlorp

GleepGlorp can propose a new knowledge base, or a change to a knowledge base's name or description. Nothing changes until you approve. It can't add folders or files, re-index or remove anything: those happen on the knowledge base's own page, so add its folders yourself after approving. Renaming one that agents use changes the name of its search tool, and the card names those agents. GleepGlorp can also fill the form without saving; nothing is stored until you choose **Create** or **Save**.

## Related topics

- "agent-tools" for attaching knowledge.
- "settings" for the indexing page.
