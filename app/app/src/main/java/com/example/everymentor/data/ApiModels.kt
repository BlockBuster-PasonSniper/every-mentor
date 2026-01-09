package com.example.everymentor.data

data class CertificationVerifyRequest(
    val type: String,
    val imageBase64: String
)

data class CertificationVerifyResponse(
    val success: Boolean,
    val extractedText: String?,
    val errorMessage: String?
)
