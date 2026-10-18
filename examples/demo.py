from polymarket_bot.cli import main
if __name__ == "__main__":
    import sys
    sys.argv = ["polymarket-bot", "run", "--mode", "demo"]
    main()
