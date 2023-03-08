# arxivbot

## Feature Requests 

- [ ] provide cleaner abstracts
  - [ ] parse URLs and hyperlink them
  - [ ] parse latex and render it as an equation
- [ ] provide integration via Telegram so that users can send their link to an authenticated channel and GitHub actions will trigger uploads nightly or, better, in response to a trigger triggered by Telegram
- [x] write abstract to entries as text
- [x] add check for duplicate entries before adding to database (i.e. if arXiv ID is already in database)

### Credentials

_credentials_template.env_ is a copy of (template for) a file, _credentials.env_, which should be placed in the same (top-level) directory with your Notion Integration token for authenticating. This is more convenient that exporting it each time you use the tool. 

### Resources

- arxiv
  - http://lukasschwab.me/arxiv.py/index.html
  - Result http://lukasschwab.me/arxiv.py/index.html#Result
  - Search http://lukasschwab.me/arxiv.py/index.html#Search
- arxiv API 
  - https://info.arxiv.org/help/api/basics.html#quickstart
  - https://info.arxiv.org/help/api/user-manual.html#sort
  - https://info.arxiv.org/help/api/user-manual.html#python_simple_example
  - 
- https://www.notion.so/my-integrations
- https://developers.notion.com/reference/update-a-database
- what you actually want - to update or add a row of a database
  - https://developers.notion.com/reference/patch-page
  - https://developers.notion.com/reference/post-page
  - info about property of page's parent db (must match) https://developers.notion.com/reference/property-object

similar projects:
- https://github.com/wangjksjtu/arxiv2notionplus
- 