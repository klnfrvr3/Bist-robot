plugins {
    id("com.android.application")
    id("com.chaquo.python")
}

val calismaNo = (System.getenv("GITHUB_RUN_NUMBER") ?: "1").toInt()

android {
    namespace = "com.bistkonsey.robot"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.bistkonsey.robot"
        minSdk = 26
        targetSdk = 34
        versionCode = calismaNo
        versionName = "1.0.$calismaNo"
        ndk {
            abiFilters.addAll(listOf("arm64-v8a", "x86_64"))
        }
    }

    // Sabit imza anahtarı: yeni sürümler eskisinin üzerine (veriler silinmeden) kurulabilsin.
    signingConfigs {
        create("bist") {
            storeFile = file("bist.keystore")
            storePassword = "bistkonsey"
            keyAlias = "bist"
            keyPassword = "bistkonsey"
        }
    }

    buildTypes {
        getByName("release") {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("bist")
        }
        getByName("debug") {
            signingConfig = signingConfigs.getByName("bist")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    lint {
        checkReleaseBuilds = false
        abortOnError = false
    }
}

chaquopy {
    defaultConfig {
        version = "3.12"
    }
}
