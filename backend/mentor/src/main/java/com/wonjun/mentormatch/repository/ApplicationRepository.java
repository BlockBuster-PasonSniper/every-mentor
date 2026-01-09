package com.wonjun.mentormatch.repository;

import com.wonjun.mentormatch.domain.application.Application;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ApplicationRepository extends JpaRepository<Application, Long> {
}
