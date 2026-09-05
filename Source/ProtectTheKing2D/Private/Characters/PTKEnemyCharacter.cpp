// Protect the King - 2D. Autonomous enemy tier.

#include "Characters/PTKEnemyCharacter.h"

#include "AIController.h"
#include "Components/CapsuleComponent.h"
#include "Components/PTKHealthComponent.h"
#include "DrawDebugHelpers.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "Engine/OverlapResult.h"
#include "Kismet/GameplayStatics.h"
#include "ProtectTheKing2D.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(PTKEnemyCharacter)

APTKEnemyCharacter::APTKEnemyCharacter(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	Team = EPTKTeam::Enemies;

	// ENEMY SCALE. Individually fragile and short-reaching; the threat comes
	// from numbers. Each enemy type sets its own MaxHealth in its Blueprint -
	// this is only the tier default.
	if (HealthComponent)
	{
		HealthComponent->SetMaxHealth(100.0f);
	}

	// One tile of reach, against a guard's 3.5. The enemy must close almost all
	// the way in before it can hit back.
	AttackRangeTiles = 1.0f;
	AttackHitWidthFactor = 0.45f;
	AttackDamage = 15.0f;

	// Enemies never own the view. Leaving the rig enabled would give every
	// spawned creature a camera competing to become the view target.
	bEnableCameraRig = false;

	// A plain AAIController, with no Behavior Tree and no navmesh. It exists
	// only so the pawn is possessed: UCharacterMovementComponent consumes the
	// accumulated control input through its controller, so AddMovementInput on
	// an unpossessed pawn would silently do nothing.
	AIControllerClass = AAIController::StaticClass();
	AutoPossessAI = EAutoPossessAI::PlacedInWorldOrSpawned;
}

void APTKEnemyCharacter::BeginPlay()
{
	Super::BeginPlay();

	Target = FindTarget();
	AttackCooldownRemaining = InitialAttackDelay;
	EnemyState = EPTKEnemyState::Idle;
}

float APTKEnemyCharacter::GetDistanceToTarget() const
{
	return Target ? FVector::Dist(GetActorLocation(), Target->GetActorLocation()) : -1.0f;
}

APTKTopDownCharacter* APTKEnemyCharacter::FindTarget() const
{
	// One enemy, one player, for this phase. Threat tables, King targeting and
	// guard selection are later work and are deliberately absent.
	APawn* const PlayerPawn = UGameplayStatics::GetPlayerPawn(this, 0);
	APTKTopDownCharacter* const Candidate = Cast<APTKTopDownCharacter>(PlayerPawn);
	return IsHostileTo(Candidate) ? Candidate : nullptr;
}

FVector2D APTKEnemyCharacter::ToScreenSpace(const FVector& WorldOffset) const
{
	// Project a world offset onto the screen basis so the result is in the same
	// convention IA_Move produces. Asking the camera rig rather than assuming
	// +X is screen-right is what keeps enemies from moving mirrored.
	return FVector2D(FVector::DotProduct(WorldOffset, MovementRightVector),
	                 FVector::DotProduct(WorldOffset, MovementUpVector));
}

FVector2D APTKEnemyCharacter::ComputeBearingTo(const APTKTopDownCharacter& InTarget) const
{
	// Pure direction to the target, with no crowd avoidance mixed in. Facing is
	// chosen from THIS rather than from the steering vector: an enemy shouldering
	// past a neighbour should still look at what it is attacking, not at wherever
	// separation happens to be pushing it.
	FVector2D Bearing = ToScreenSpace(InTarget.GetActorLocation() - GetActorLocation());
	const float Size = Bearing.Size();
	return (Size > KINDA_SMALL_NUMBER) ? (Bearing / Size) : FVector2D::ZeroVector;
}

FVector2D APTKEnemyCharacter::ComputeSeparation() const
{
	// Deliberately not flocking - no alignment, no cohesion, no neighbour lists.
	// Just a short push away from anyone standing too close, which is enough to
	// stop ten creatures converging on one point and jamming.
	//
	// The query is a sphere overlap rather than an actor iteration so the cost
	// stays with the physics broadphase instead of growing with level size.
	UWorld* const World = GetWorld();
	if (!World || SeparationRadius <= 0.0f)
	{
		return FVector2D::ZeroVector;
	}

	TArray<FOverlapResult> Overlaps;
	FCollisionQueryParams Params(SCENE_QUERY_STAT(PTKEnemySeparation), false, this);
	Params.AddIgnoredActor(this);

	World->OverlapMultiByObjectType(
		Overlaps, GetActorLocation(), FQuat::Identity,
		FCollisionObjectQueryParams(ECC_Pawn),
		FCollisionShape::MakeSphere(SeparationRadius), Params);

	FVector2D Push = FVector2D::ZeroVector;
	for (const FOverlapResult& Result : Overlaps)
	{
		const APTKEnemyCharacter* const Other = Cast<APTKEnemyCharacter>(Result.GetActor());
		if (!Other || Other == this || Other->IsDead())
		{
			continue;
		}

		const FVector Away = GetActorLocation() - Other->GetActorLocation();
		const float Distance = Away.Size();
		if (Distance <= KINDA_SMALL_NUMBER)
		{
			// Exactly co-located - two spawns landed on the same point. Any
			// direction will do, but it must be deterministic per pair or the
			// pair will jitter against each other forever.
			Push += FVector2D(GetUniqueID() % 2 ? 1.0f : -1.0f, 0.0f);
			continue;
		}
		if (Distance >= SeparationRadius)
		{
			continue;
		}

		// Linear falloff: touching pushes hardest, at the radius it is zero.
		const float Strength = 1.0f - (Distance / SeparationRadius);
		Push += ToScreenSpace(Away / Distance) * Strength;
	}
	return Push;
}

FVector2D APTKEnemyCharacter::ComputeDesiredInput(const APTKTopDownCharacter& InTarget) const
{
	// Straight-line steering across open ground, nudged sideways by anyone in
	// the way. The arena has no lanes yet; when the real path system lands, this
	// is the only method that changes.
	FVector2D Input = ComputeBearingTo(InTarget) + ComputeSeparation() * SeparationWeight;

	const float Size = Input.Size();
	return (Size > KINDA_SMALL_NUMBER) ? (Input / Size) : FVector2D::ZeroVector;
}

void APTKEnemyCharacter::HandleDeath(AActor* Killer)
{
	// Clear the AI first so nothing below can re-enter Chase or Attack while
	// the base class is tearing the character down.
	EnemyState = EPTKEnemyState::Dead;
	Target = nullptr;
	AttackCooldownRemaining = 0.0f;

	Super::HandleDeath(Killer);
}

void APTKEnemyCharacter::Tick(float DeltaSeconds)
{
	// The base Tick runs the movement, facing and animation state machine, and
	// returns immediately once dead. The AI below only decides what to feed it.
	Super::Tick(DeltaSeconds);

	if (EnemyState == EPTKEnemyState::Dead || IsDead())
	{
		return;
	}

	if (AttackCooldownRemaining > 0.0f)
	{
		AttackCooldownRemaining = FMath::Max(0.0f, AttackCooldownRemaining - DeltaSeconds);
	}

	TargetRefreshTimer -= DeltaSeconds;
	if (!Target || Target->IsDead() || TargetRefreshTimer <= 0.0f)
	{
		TargetRefreshTimer = TargetRefreshInterval;
		Target = FindTarget();
	}

	// Once a second, on one line: everything needed to answer "why is it not
	// attacking" without attaching a debugger or reading the on-screen panel.
	DiagnosticTimer -= DeltaSeconds;
	if (DiagnosticTimer <= 0.0f)
	{
		DiagnosticTimer = 1.0f;
		UE_LOG(LogPTK, Verbose,
			TEXT("%s state=%s target=%s dist=%.0f controller=%s speed=%.0f cd=%.2f"),
			*GetName(), *UPTKTypesLibrary::EnemyStateToString(EnemyState),
			*GetNameSafe(Target), GetDistanceToTarget(),
			*GetNameSafe(GetController()), GetVelocity().Size(),
			AttackCooldownRemaining);
	}

	if (bDrawPerceptionRanges)
	{
		const FVector Centre = GetActorLocation();
		const FVector Axis = MovementDepthVector.GetSafeNormal();
		DrawDebugCircle(GetWorld(), Centre, DetectionRange, 48, FColor(60, 60, 200), false, -1.0f, 0,
			1.0f, MovementRightVector, MovementUpVector, false);
		DrawDebugCircle(GetWorld(), Centre, GetAttackReach(), 32, FColor::Red, false, -1.0f, 0,
			1.0f, MovementRightVector, MovementUpVector, false);
		(void)Axis;
	}

	// An attack owns the character until its animation finishes. Not steering
	// during it is what makes the enemy plant itself and swing instead of
	// sliding forward mid-strike.
	if (IsAttacking())
	{
		SetMoveInput(FVector2D::ZeroVector);
		return;
	}

	if (!Target)
	{
		EnemyState = EPTKEnemyState::Idle;
		SetMoveInput(FVector2D::ZeroVector);
		return;
	}

	const float Distance = FVector::Dist(GetActorLocation(), Target->GetActorLocation());

	if (Distance > DetectionRange)
	{
		// Out of range entirely: stand still rather than drifting toward a
		// target the enemy is not supposed to have noticed.
		EnemyState = EPTKEnemyState::Idle;
		SetMoveInput(FVector2D::ZeroVector);
		return;
	}

	// The tolerance band stops a target hovering exactly on AttackRange from
	// flipping the state - and therefore the animation - every single frame.
	// The stop distance IS the attack reach, so the enemy can never halt
	// somewhere its own swing cannot land.
	const float Reach = GetAttackReach();
	const float LeaveRange = Reach + AttackRangeTolerance;
	const bool bInRange = (EnemyState == EPTKEnemyState::Attack)
		? (Distance <= LeaveRange)
		: (Distance <= Reach);

	if (!bInRange)
	{
		EnemyState = EPTKEnemyState::Chase;
		SetMoveInput(ComputeDesiredInput(*Target));
		return;
	}

	// In range: stop, face the target, swing when recovered.
	EnemyState = EPTKEnemyState::Attack;
	SetMoveInput(FVector2D::ZeroVector);

	// Facing still has to be updated even though there is no movement input,
	// because the base class only refreshes it while moving. Feeding the
	// direction-from-input rule the same vector chase would have used keeps the
	// enemy's attack facing consistent with its walk facing.
	const FVector2D Bearing = ComputeBearingTo(*Target);
	SetFacingDirection(UPTKTypesLibrary::DirectionFromInput(
		Bearing, GetFacingDirection(), MoveDeadZone, FacingHysteresis));

	if (AttackCooldownRemaining <= 0.0f)
	{
		if (StartAttack())
		{
			// Cooldown is measured from the end of the swing, so it reads as
			// recovery rather than as an overlapping timer.
			AttackCooldownRemaining = AttackCooldown + AttackTimeRemaining;
		}
	}
}
