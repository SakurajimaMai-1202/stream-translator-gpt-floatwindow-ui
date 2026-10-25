package com.streamtranslator.subtitle

import org.junit.Assert.*
import org.junit.Test

class ProtocolTest {
    @Test fun normalizeAddresses() {
        val cases = mapOf(
            "" to "", " 192.168.1.10 " to "http://192.168.1.10:8765",
            "192.168.1.10:8765" to "http://192.168.1.10:8765",
            "https://host" to "https://host",
            "https://host:9443" to "https://host:9443",
            "my_pc:8765" to "http://my_pc:8765",
            "http://my_pc" to "http://my_pc:8765",
            "https://my_pc" to "https://my_pc",
            "http://host:9000" to "http://host:9000",
            "host:8765?x=y" to "http://host:8765",
            "https://host/prefix/mobile?x=1#fragment" to "https://host/prefix",
            "http://host:80/desktop/" to "http://host:80",
            "http://[::1]:8765/subtitle" to "http://[::1]:8765",
            "HTTP://host:8765/prefix/" to "http://host:8765/prefix",
            "http://host:8765/prefix%20name/mobile" to "http://host:8765/prefix%20name"
        )
        cases.forEach { (input, expected) -> assertEquals(input, expected, normalizeServerUrl(input)) }
    }
    @Test fun rejectInvalidAddresses() {
        listOf("http://my_pc:abc", "http://my_pc:99999999999999", "http://my_pc:", "http://user@my_pc", "ftp://host", "mailto:host", "http://user:pass@host", "http://host:65536", "http://host:abc", "host:123/a b", "http://", "http://host:").forEach {
            assertThrows(it, IllegalArgumentException::class.java) { normalizeServerUrl(it) }
        }
    }
    @Test fun matchSegmentBeforeTimestampAndId() {
        val rows = listOf(mapOf("segment_id" to 7, "timestamp" to "a"), mapOf("segment_id" to 8, "timestamp" to "b"))
        assertEquals(0, SubtitleHistory.findIndex(rows, mapOf("segment_id" to "7", "timestamp" to "b")))
        assertEquals(1, SubtitleHistory.findIndex(rows, mapOf("timestamp" to "b")))
        assertEquals(0, SubtitleHistory.findIndex(listOf(mapOf("id" to 0)), mapOf("id" to "0")))
        assertEquals(-1, SubtitleHistory.findIndex(rows, mapOf("segment_id" to 9)))
        assertEquals(-1, SubtitleHistory.findIndex(rows, emptyMap()))
    }
    @Test fun backendTimestampHasPriority() {
        assertEquals(0, SubtitleHistory.findIndex(listOf(mapOf("backend_timestamp" to "server", "timestamp" to "local")), mapOf("timestamp" to "server")))
        assertEquals(-1, SubtitleHistory.findIndex(listOf(mapOf("backend_timestamp" to "server", "timestamp" to "local")), mapOf("timestamp" to "local")))
    }
    @Test fun transitionWithOneMillisecondRounding() {
        val original = mapOf("original" to " 字幕 ", "timestamp" to "00:00:01,000 --> 00:00:02,000")
        val incoming = mapOf("segment_id" to 1, "original" to "字幕", "backend_timestamp" to "00:00:01.001 → 00:00:01.999", "translated" to "翻譯")
        assertEquals(0, SubtitleHistory.findIndex(listOf(original), incoming))
        val merged = SubtitleHistory.merge(listOf(original), incoming)
        assertEquals(1, merged.size)
        assertEquals("翻譯", merged.single()["translated"])
        assertEquals(1, merged.single()["segment_id"])
        assertEquals(original["timestamp"], merged.single()["timestamp"])
    }
    @Test fun driftToleranceAndNewestCandidateMatchPython() {
        val row = mapOf("original" to "same", "timestamp" to "0:00:01,0 -> 0:00:02,0")
        fun update(start: String, end: String, original: String = "same") = mapOf("original" to original, "timestamp" to "00:00:$start --> 00:00:$end")
        assertEquals(1, SubtitleHistory.findIndex(listOf(row, row), update("01.050", "02.050")))
        assertEquals(-1, SubtitleHistory.findIndex(listOf(row), update("01.051", "02.000")))
        assertEquals(-1, SubtitleHistory.findIndex(listOf(row), update("01.000", "02.051")))
        assertEquals(-1, SubtitleHistory.findIndex(listOf(row), update("01.001", "02.001", "different")))
        assertEquals(-1, SubtitleHistory.findIndex(listOf(row), mapOf("original" to "same", "timestamp" to "invalid")))
    }
    @Test fun historyIsBoundedAndPartialUpdatesPreserveOtherFields() {
        var rows: List<Subtitle> = emptyList()
        repeat(10) { rows = SubtitleHistory.merge(rows, mapOf("segment_id" to it, "original" to "text"), 3) }
        assertEquals(listOf(7, 8, 9), rows.map { it["segment_id"] })
        rows = SubtitleHistory.merge(rows, mapOf("segment_id" to 8, "translated" to "result"), 3)
        assertEquals("text", rows[1]["original"])
        assertEquals("result", rows[1]["translated"])
    }
    @Test fun sseMultilineCommentsAndReset() {
        val parser = SseLineParser()
        listOf("\uFEFF: ping", "event: subtitle", "data: first", ": comment", "data:  second", "id: ignored").forEach { assertNull(parser.line(it)) }
        assertEquals(SseEvent("subtitle", "first\n second"), parser.line(""))
        parser.line("data: next")
        assertEquals(SseEvent("message", "next"), parser.line(""))
    }
    @Test fun sseEventWithoutDataIsNotDispatched() {
        val parser = SseLineParser()
        parser.line("event: status")
        assertNull(parser.line(""))
        parser.line(": ping")
        assertNull(parser.line(""))
        parser.line("data")
        assertEquals(SseEvent("message", ""), parser.line(""))
    }
    @Test fun reconnectSequenceAndReset() {
        val backoff = ReconnectBackoff()
        assertEquals(listOf(1000L, 2000L, 5000L, 10000L, 10000L, 10000L), List(6) { backoff.nextDelayMs() })
        backoff.reset()
        assertEquals(1000L, backoff.nextDelayMs())
    }

    @Test fun boundedBodiesAndLines() {
        assertEquals(MAX_BODY_BYTES, readLimitedBody(okio.Buffer().writeUtf8("a".repeat(MAX_BODY_BYTES))).length)
        assertThrows(java.io.IOException::class.java) {
            readLimitedBody(okio.Buffer().writeUtf8("a".repeat(MAX_BODY_BYTES + 1)))
        }
        assertEquals(MAX_LINE_BYTES.toInt(), okio.Buffer().writeUtf8("a".repeat(MAX_LINE_BYTES.toInt()) + "\r\n").readUtf8LineStrict(MAX_LINE_BYTES).length)
        assertThrows(java.io.IOException::class.java) {
            okio.Buffer().writeUtf8("a".repeat(MAX_LINE_BYTES.toInt() + 1) + "\n").readUtf8LineStrict(MAX_LINE_BYTES)
        }
        assertThrows(java.io.IOException::class.java) {
            okio.Buffer().writeUtf8("a".repeat(MAX_LINE_BYTES.toInt() + 1)).readUtf8LineStrict(MAX_LINE_BYTES)
        }
    }
    @Test fun eventLimitCountsUtf8AndResetsAfterDispatch() {
        val parser = SseLineParser()
        val data = "data: " + "a".repeat(256 * 1024 - 1)
        repeat(4) { parser.line(data) }
        assertNotNull(parser.line(""))
        parser.line(data)
        assertNotNull(parser.line(""))
        repeat(4) { parser.line(data) }
        assertThrows(java.io.IOException::class.java) { parser.line("data: x") }
        val unicode = SseLineParser()
        assertThrows(java.io.IOException::class.java) { repeat(6) { unicode.line("data: " + "\u4e2d".repeat(65536)) } }
    }
    @Test fun shortPingStreamsKeepBackoffAndValidEventsResetOnlyOnce() {
        val backoff = ReconnectBackoff()
        repeat(3) { attempt ->
            val health = StreamHealth(0)
            assertFalse(health.shouldReset(false, 1_000_000_000))
            assertEquals(listOf(1000L, 2000L, 5000L)[attempt], backoff.nextDelayMs())
        }
        val health = StreamHealth(0)
        assertTrue(health.shouldReset(true, 1))
        backoff.reset()
        assertFalse(health.shouldReset(true, 2))
        assertEquals(1000L, backoff.nextDelayMs())
        assertTrue(StreamHealth(0).shouldReset(false, 5_000_000_000))
    }
    @Test fun statusThenDisconnectKeepsGrowingBackoff() {
        val backoff = ReconnectBackoff()
        val delays = List(5) {
            val health = StreamHealth(0)
            if (health.shouldReset("status", 100_000_000)) backoff.reset()
            if (health.shouldReset(false, 200_000_000)) backoff.reset()
            backoff.nextDelayMs()
        }
        assertEquals(listOf(1000L, 2000L, 5000L, 10000L, 10000L), delays)
        assertTrue(StreamHealth(0).shouldReset("subtitle", 1))
        assertTrue(StreamHealth(0).shouldReset("status", 5_000_000_000))
    }
    @Test fun errorBodyPrefixIgnoresOverflow() {
        val source = okio.Buffer().writeUtf8("x".repeat(MAX_BODY_BYTES + 1))
        assertEquals(4096, readErrorPrefix(source).length)
        assertEquals((MAX_BODY_BYTES + 1 - 4096).toLong(), source.size)
    }
    @Test fun autoConnectRequiresSavedValidAddressAndPreference() {
        val saved = "http://localhost:8765"
        assertEquals(saved, autoConnectServer(saved, true, true, false))
        assertEquals(saved, autoConnectServer(saved, true, false, true))
        assertNull(autoConnectServer(saved, true, false, false))
        for (fresh in listOf(true, false)) {
            assertNull(autoConnectServer(saved, false, fresh, true))
            assertNull(autoConnectServer("http://", true, fresh, true))
            assertNull(autoConnectServer("", true, fresh, true))
        }
    }
    @Test fun staleConnectionCannotWriteAfterDisconnectOrSwitch() {
        val generations = ConnectionGeneration()
        val old = generations.advance()
        var state = "old"
        generations.apply(old) { state = "connected" }
        assertEquals("connected", state)
        val next = generations.advance()
        generations.apply(old) { state = "stale subtitle" }
        assertEquals("connected", state)
        generations.apply(next) { state = "new host" }
        generations.advance()
        generations.apply(next) { state = "stale readiness" }
        assertEquals("new host", state)
    }
    @Test fun staleNotificationActionsCannotCreateOverlay() {
        listOf(null, "com.streamtranslator.subtitle.TOUCH", "com.streamtranslator.subtitle.STOP", "com.streamtranslator.subtitle.REPOST").forEach {
            assertFalse(overlayActionAllowed(false, it))
            assertTrue(overlayActionAllowed(true, it))
        }
        assertTrue(overlayActionAllowed(false, "com.streamtranslator.subtitle.START"))
    }
    @Test fun removalFailureStillReleasesAndFinishes() {
        val steps = mutableListOf<String>()
        releaseOverlaySafely({ throw IllegalArgumentException("removed") }, { steps += "release" }, { steps += "finish" })
        assertEquals(listOf("release", "finish"), steps)
    }
    @Test fun overlayDefaultsAreTransparentOutlinedAndLimitedToTwoEntries() {
        val settings = SubtitleSettings()
        assertEquals(100, settings.backgroundOpacity)
        assertEquals(0, settings.overlayBackgroundOpacity)
        assertEquals("#000000", settings.backgroundColor)
        assertEquals(3, settings.strokeWidth)
        assertEquals(4, settings.shadowRadius)
        assertEquals(2, settings.overlayDisplayCount)
        assertEquals(92, settings.overlayWidth)
        assertEquals(5, settings.maxDisplayCount)
    }
}
