import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
}

// Release signing reads a properties file kept outside the repo
// (storeFile, storePassword, keyAlias, keyPassword). Point to it with the
// gradle property or env var STREAM_TRANSLATOR_SIGNING; without it the release APK stays unsigned.
val signingPropsPath = (findProperty("STREAM_TRANSLATOR_SIGNING") as String?)
    ?: System.getenv("STREAM_TRANSLATOR_SIGNING")
val signingProps = signingPropsPath?.let { path ->
    file(path).takeIf { it.isFile }?.let { f -> Properties().apply { f.inputStream().use { load(it) } } }
}
android {
    namespace = "com.streamtranslator.subtitle"
    compileSdk = 36
    defaultConfig {
        applicationId = "com.streamtranslator.subtitle"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "1.6.1"
    }
    signingConfigs {
        if (signingProps != null) {
            create("release") {
                storeFile = file(signingProps.getProperty("storeFile"))
                storePassword = signingProps.getProperty("storePassword")
                keyAlias = signingProps.getProperty("keyAlias")
                keyPassword = signingProps.getProperty("keyPassword")
            }
        }
    }
    buildTypes {
        release {
            if (signingProps != null) signingConfig = signingConfigs.getByName("release")
        }
    }
    testOptions { unitTests.isIncludeAndroidResources = true }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
kotlin { jvmToolchain(17) }
dependencies {
    implementation(libs.androidx.core)
    implementation(libs.androidx.appcompat)
    implementation(libs.material)
    implementation(libs.lifecycle.runtime)
    implementation(libs.lifecycle.service)
    implementation(libs.coroutines)
    implementation(libs.okhttp)
    testImplementation(libs.junit)
    testImplementation(libs.robolectric)
    testImplementation(libs.mockwebserver)
}
