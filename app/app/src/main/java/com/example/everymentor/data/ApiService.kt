package com.example.everymentor.data

import retrofit2.http.Body
import retrofit2.http.POST

interface ApiService {

    @POST("/api/certifications/verify")
    suspend fun verifyCertification(
        @Body request: CertificationVerifyRequest
    ): CertificationVerifyResponse
}
