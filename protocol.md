# Network protocol
- Big-endian byte order is used
- All values are unsigned integers unless specified otherwise


## Client messages

### Join
```
1 | 0x00
1 | n
n | name (UTF-8 string)
```
- Response is `Join OK` or `Action rejected`

### Ready
```
1 | 0x01
```

### Keep-alive
```
1 | 0x02
```

### Leave
```
1 | 0x03
```

### Tile exchange
```
1 | 0x04
1 | n
repeat n times:
    1 | tile ID
```
- Response is `End turn` or `Action rejected`

### Place tiles
```
1 | 0x05
1 | n
repeat n times:
    1 | position (column count * row + column)
    1 | tile ID
    1 | m
    m | letter (UTF-8 symbol)
```
- `n` = 0 means skip turn
- `m` and `letter` are ignored if tile is not blank
- Response is `End turn` or `Action rejected`

### Chat
```
1 | 0x06
2 | n
n | text (UTF-8 string)
```


## Server messages

### Join OK
```
1 | 0x07
1 | player ID
1 | n
repeat n times:
    1 | player ID
    1 | ready
    1 | m
    m | name (UTF-8 string)
```
- Only sent to player who sent `Join`
- First `Player ID` is ID of player who sent `Join`
- All players are listed including sender of `Join`

### Action rejected
```
1 | 0x08
2 | n
n | reason (UTF-8 string)
```

### Player joined
```
1 | 0x09
1 | player ID
1 | n
n | name (UTF-8 string)
```
- Not sent to player who sent `Join`

### Player left
```
1 | 0x0A
1 | player ID
```

### Player ready
```
1 | 0x0B
1 | player ID
```
- If there are at least 2 players and all players have toggled ready, `Start turn` is sent instead

### Start turn
```
1 | 0x0C
1 | player ID
2 | timer
1 | tiles left
1 | n
repeat n times:
    1 | tile ID
    1 | points
    1 | m
    m | letter (UTF-8 symbol)
```
- `player ID` is the ID of the player whose turn it is
- `timer` is the amount of seconds before the player skips their turn
- `timer` = 0 means no limit
- `tiles left` is the amount of drawable tiles left
- `n` is the amount of tiles on the player's rack
- `m` = 0 means blank tile

### End turn
```
1 | 0x0D
1 | player ID
2 | score
1 | n
repeat n times:
    1 | position (column count * row + column)
    1 | points
    1 | m
    m | letter (UTF-8 symbol)
```
- `player ID` is the ID of the player who completed their turn
- `score` is the total score of the player who completed their turn
- `n` is the amount of new tiles on the board
- If all players have skipped their last turn, `End game` is sent instead

### End game
```
1 | 0x0E
1 | n
repeat n times:
    1 | player ID
    2 | score
```

### Shutdown
```
1 | 0x0F
```

### Player chat
```
1 | 0x10
1 | player ID
2 | n
n | text (UTF-8 string)
```

### Notification
```
1 | 0x11
2 | n
n | text (UTF-8 string)
```