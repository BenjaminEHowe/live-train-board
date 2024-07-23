import badger_ldb


def time(twenty_four_hour_time):
    hour = int(twenty_four_hour_time[0:2])
    minute = int(twenty_four_hour_time[2:4])
    return (2020, 1, 1, hour, minute, 14, 2, 1)


print("Should be awake at midday with overnight sleep window")
assert badger_ldb.should_be_in_sleep_mode(
    start_hour = 18,
    end_hour = 08,
    current_time = time("1200")
) == False

print("Should be asleep at midnight with overnight sleep window")
assert badger_ldb.should_be_in_sleep_mode(
    start_hour = 18,
    end_hour = 08,
    current_time = time("0000")
) == True

print("Should be awake at midnight with daytime sleep window")
assert badger_ldb.should_be_in_sleep_mode(
    start_hour = 08,
    end_hour = 18,
    current_time = time("0000")
) == False

print("Should be asleep at midday with daytime sleep window")
assert badger_ldb.should_be_in_sleep_mode(
    start_hour = 08,
    end_hour = 18,
    current_time = time("1200")
) == True

print("Should handle same-hour sleep window (asleep)")
assert badger_ldb.should_be_in_sleep_mode(
    start_hour = 12,
    start_minute = 15,
    end_hour = 12,
    end_minute = 45,
    current_time = time("1230")
) == True

print("Should handle same-hour sleep window (awake, before window)")
assert badger_ldb.should_be_in_sleep_mode(
    start_hour = 12,
    start_minute = 15,
    end_hour = 12,
    end_minute = 30,
    current_time = time("1200")
) == False

print("Should handle same-hour sleep window (awake, after window)")
assert badger_ldb.should_be_in_sleep_mode(
    start_hour = 12,
    start_minute = 15,
    end_hour = 12,
    end_minute = 30,
    current_time = time("1245")
) == False
