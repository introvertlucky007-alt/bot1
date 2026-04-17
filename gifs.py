import random

GIFS = {

    # 🏏 UMPIRE
    "out_signal": [
        "https://tenor.com/tJB7nPY10ZH.gif",
        "https://tenor.com/oHTDweE8nPs.gif"
    ],

    # 🏃 BOWLING ACTION
    "pace": [
        "https://media1.giphy.com/media/v1.Y2lkPTc5MGI3NjExa3kzemRndzFsbTgzbHZlbXZqcXFtdmY1ZDZhZm0wMWcyZGJxajF4dCZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/sqLbmNWyVFeUj9ohWj/giphy.gif",
        "https://media1.giphy.com/media/v1.Y2lkPTc5MGI3NjExa3kzemRndzFsbTgzbHZlbXZqcXFtdmY1ZDZhZm0wMWcyZGJxajF4dCZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/sqLbmNWyVFeUj9ohWj/giphy.gif"
    ],

    "spin": [
        "https://tenor.com/n1yf92jq7GE.gif",
        "https://tenor.com/n1yf92jq7GE.gif"
    ],

    # 🔥 BOUNDARIES
    "four": [
        "https://jumpshare.com/share/uRr9Vmawfhb6UvNoBQ26",
        "https://tenor.com/lM5WxVKtORb.gif"
    ],

    "six": [
        "https://tenor.com/bCj4b.gif",
        "https://tenor.com/bAwX6.gif"
    ],

    # 💀 WICKETS
    "bowled": [
        "https://tenor.com/oaclEF9ed2N.gif"
    ],

    "caught": [
        "https://tenor.com/so3BgXe8v5v.gif"
    ],

    "stumped": [
        "https://tenor.com/fh0GQoSPXxp.gif"
    ],

    # 🏁 INNINGS END
    "innings_end": [
        "https://tenor.com/jaP7XmFGKif.gif"
    ],

    # 🏆 MATCH RESULT
    "celebration": [
        "https://tenor.com/bsdCe.gif"
    ],

    "restricted": [
        "https://tenor.com/inNkn3zhTxF.gif"
    ]
}


def get_gif(category):
    gifs = GIFS.get(category, [])
    if not gifs:
        return None
    return random.choice(gifs)