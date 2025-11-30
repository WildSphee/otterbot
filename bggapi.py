from boardgamegeek import BGGClient

bgg = BGGClient()

# Search for game
game = bgg.game("Carcassonne")

print(f"Name: {game.name}")
print(f"Year: {game.year}")
print(f"Rating: {game.rating_average}")
print(f"Players: {game.min_players}-{game.max_players}")
print(f"Playing Time: {game.playing_time} minutes")
