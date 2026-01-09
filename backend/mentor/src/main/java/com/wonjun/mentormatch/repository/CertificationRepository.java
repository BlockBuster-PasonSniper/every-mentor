package com.wonjun.mentormatch.repository;

import com.wonjun.mentormatch.domain.member.Certification;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CertificationRepository extends JpaRepository<Certification, Long> {
}
