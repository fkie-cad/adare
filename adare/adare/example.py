from adare.database.api.serialize import SerializeApi

def main():
    # Keep the program running
    with SerializeApi() as db:
        print(db.serialize_run_by_ulid('01J17Z6F9W94X18ZASQ62MJK29'))

if __name__ == '__main__':
    main()
