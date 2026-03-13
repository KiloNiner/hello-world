#!/usr/bin/osascript
-- top_senders.applescript
-- Scans iCloud INBOX and Exchange Indbakke and prints top N senders by message count.

set topN to 50

-- Collect all senders
set allSenders to {}

tell application "Mail"
	set inbox1 to mailbox "INBOX" of account "iCloud"
	set inbox2 to mailbox "Indbakke" of account "Exchange"

	repeat with msg in (messages of inbox1)
		set end of allSenders to sender of msg
	end repeat

	repeat with msg in (messages of inbox2)
		set end of allSenders to sender of msg
	end repeat
end tell

-- Count occurrences per sender
set senderNames to {}
set senderCounts to {}

repeat with s in allSenders
	set sStr to s as string
	set found to false
	repeat with i from 1 to count of senderNames
		if item i of senderNames is sStr then
			set item i of senderCounts to (item i of senderCounts) + 1
			set found to true
			exit repeat
		end if
	end repeat
	if not found then
		set end of senderNames to sStr
		set end of senderCounts to 1
	end if
end repeat

-- Sort descending by count (bubble sort)
set n to count of senderNames
repeat with i from 1 to n - 1
	repeat with j from 1 to n - i
		if item j of senderCounts < item (j + 1) of senderCounts then
			-- swap counts
			set tmpC to item j of senderCounts
			set item j of senderCounts to item (j + 1) of senderCounts
			set item (j + 1) of senderCounts to tmpC
			-- swap names
			set tmpN to item j of senderNames
			set item j of senderNames to item (j + 1) of senderNames
			set item (j + 1) of senderNames to tmpN
		end if
	end repeat
end repeat

-- Output top N
set limit to topN
if (count of senderNames) < limit then set limit to count of senderNames

set output to "=== Top " & limit & " Senders ===" & linefeed
repeat with i from 1 to limit
	set output to output & i & ". [" & item i of senderCounts & "] " & item i of senderNames & linefeed
end repeat

log output
return output
