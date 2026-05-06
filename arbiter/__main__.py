from importlib.metadata import PackageNotFoundError, version

try:
    from arbiter import __version__
except ImportError:
    try:
        __version__ = version("the-arbiter")
    except PackageNotFoundError:
        __version__ = "0.1.0"


def main() -> None:
    print(f"The Arbiter {__version__}")
    print("Launch the Streamlit workspace with:")
    print("  python -m streamlit run arbiter/app/streamlit_app.py")
    print("Launch the API with:")
    print("  python arbiter/api/run_server.py")


if __name__ == "__main__":
    main()
